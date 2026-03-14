"""Control de presupuesto LLM — rate limiting con Redis."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.config import settings

log = logging.getLogger(__name__)


class LLMBudget:
    """Controla RPM y RPD de Gemini via Redis (soporta free y paid tier).

    RPD usa claves con fecha (llm:gemini:rpd:2026-03-06) para que el
    contador se reinicie automaticamente cada dia sin depender de TTL.
    """

    RPM_KEY = "llm:gemini:rpm"
    RPD_KEY_PREFIX = "llm:gemini:rpd"
    _LEGACY_RPD_KEY = "llm:gemini:rpd"  # clave vieja sin fecha

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._cleaned_legacy = False

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    def _rpd_key(self, strategy_id: str | None = None) -> str:
        """Clave RPD con fecha de hoy (y opcionalmente por estrategia)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if strategy_id:
            return f"{self.RPD_KEY_PREFIX}:{today}:{strategy_id}"
        return f"{self.RPD_KEY_PREFIX}:{today}"

    async def _cleanup_legacy_key(self) -> None:
        """Elimina la clave RPD vieja sin fecha (solo la primera vez)."""
        if self._cleaned_legacy:
            return
        try:
            r = await self._get_redis()
            deleted = await r.delete(self._LEGACY_RPD_KEY)
            if deleted:
                log.info("Clave RPD legacy eliminada: %s", self._LEGACY_RPD_KEY)
            self._cleaned_legacy = True
        except Exception:
            log.exception("Error limpiando clave RPD legacy")

    async def can_call(self) -> bool:
        """Verifica si se puede hacer una llamada sin exceder limites."""
        try:
            await self._cleanup_legacy_key()
            r = await self._get_redis()
            rpm = int(await r.get(self.RPM_KEY) or 0)
            rpd = int(await r.get(self._rpd_key()) or 0)
            can = rpm < settings.llm_max_rpm and rpd < settings.llm_max_rpd
            if not can:
                log.warning("Limite LLM alcanzado: RPM=%d/%d, RPD=%d/%d",
                            rpm, settings.llm_max_rpm, rpd, settings.llm_max_rpd)
            return can
        except Exception:
            log.exception("Error verificando presupuesto LLM")
            return False

    async def can_call_for_strategy(self, strategy_id: str, fraction: float) -> bool:
        """Verifica si una estrategia puede hacer una llamada dentro de su asignacion."""
        try:
            await self._cleanup_legacy_key()
            r = await self._get_redis()

            # Verificar RPM global
            rpm = int(await r.get(self.RPM_KEY) or 0)
            if rpm >= settings.llm_max_rpm:
                return False

            # Verificar RPD global
            rpd_global = int(await r.get(self._rpd_key()) or 0)
            if rpd_global >= settings.llm_max_rpd:
                log.warning("Limite LLM global alcanzado: RPD=%d/%d",
                            rpd_global, settings.llm_max_rpd)
                return False

            # Verificar RPD per-estrategia
            rpd_strategy = int(await r.get(self._rpd_key(strategy_id)) or 0)
            strategy_limit = int(settings.llm_max_rpd * fraction)
            if rpd_strategy >= strategy_limit:
                log.warning(
                    "Estrategia %s: presupuesto LLM agotado (%d/%d, %.0f%% de %d total)",
                    strategy_id, rpd_strategy, strategy_limit,
                    fraction * 100, settings.llm_max_rpd,
                )
                return False

            return True
        except Exception:
            log.exception("Error verificando presupuesto LLM para estrategia %s", strategy_id)
            return False

    async def record_call(self) -> None:
        """Registra una llamada al LLM (global)."""
        try:
            r = await self._get_redis()
            rpd_key = self._rpd_key()
            pipe = r.pipeline()
            pipe.incr(self.RPM_KEY)
            pipe.expire(self.RPM_KEY, 60)
            pipe.incr(rpd_key)
            pipe.expire(rpd_key, 90000)  # 25h TTL (auto-limpieza)
            await pipe.execute()
        except Exception:
            log.exception("Error registrando llamada LLM")

    async def record_call_for_strategy(self, strategy_id: str) -> None:
        """Registra una llamada para presupuesto global Y per-estrategia."""
        try:
            r = await self._get_redis()
            rpd_global = self._rpd_key()
            rpd_strategy = self._rpd_key(strategy_id)
            pipe = r.pipeline()
            # RPM global
            pipe.incr(self.RPM_KEY)
            pipe.expire(self.RPM_KEY, 60)
            # RPD global
            pipe.incr(rpd_global)
            pipe.expire(rpd_global, 90000)
            # RPD per-estrategia
            pipe.incr(rpd_strategy)
            pipe.expire(rpd_strategy, 90000)
            await pipe.execute()
        except Exception:
            log.exception("Error registrando llamada LLM para estrategia %s", strategy_id)

    async def get_usage(self) -> dict:
        """Retorna uso actual."""
        try:
            r = await self._get_redis()
            rpm = int(await r.get(self.RPM_KEY) or 0)
            rpd = int(await r.get(self._rpd_key()) or 0)
            return {
                "rpm": rpm,
                "rpm_limit": settings.llm_max_rpm,
                "rpd": rpd,
                "rpd_limit": settings.llm_max_rpd,
            }
        except Exception:
            return {"rpm": 0, "rpm_limit": settings.llm_max_rpm,
                    "rpd": 0, "rpd_limit": settings.llm_max_rpd}

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
