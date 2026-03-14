"""Tracker de costos operativos — APIs, LLM, fees de trading."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CostLog

log = logging.getLogger(__name__)


class CostTracker:
    """Registra costos operativos del agente."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_cost(
        self,
        cost_type: str,
        provider: str,
        amount_usd: float,
        detail: str | None = None,
    ) -> None:
        """Registra un costo."""
        if amount_usd <= 0:
            return
        cost = CostLog(
            cost_type=cost_type,
            provider=provider,
            amount_usd=amount_usd,
            detail=detail,
        )
        self._session.add(cost)
        log.debug("Costo registrado: %s/%s $%.6f", cost_type, provider, amount_usd)

    async def log_trading_fee(self, exchange: str, fee_usd: float) -> None:
        """Registra fee de trading."""
        await self.log_cost("trading_fee", exchange, fee_usd)

    async def log_llm_call(
        self, model: str, tokens_in: int, tokens_out: int
    ) -> None:
        """Registra costo de una llamada LLM.

        Gemini 2.5 Pro pricing (si se excede free tier):
        - Input: $1.25 / 1M tokens
        - Output: $10.00 / 1M tokens
        En free tier el costo real es $0, pero lo registramos para tracking.
        """
        # Precios de Gemini 2.5 Pro
        cost_in = (tokens_in / 1_000_000) * 1.25
        cost_out = (tokens_out / 1_000_000) * 10.00
        total = cost_in + cost_out

        await self.log_cost(
            "llm",
            model,
            total,
            detail=f"tokens_in={tokens_in},tokens_out={tokens_out}",
        )

    async def log_cycle_costs(self) -> None:
        """Registra costos estimados de un ciclo completo.

        En free tier, los costos principales son $0 para APIs.
        Registramos un costo mínimo de infraestructura para tracking.
        """
        # Costo estimado de infraestructura por ciclo (electricidad + desgaste)
        # Asumiendo ~$0.01/hora de compute → ~$0.002 por ciclo de 10 min
        await self.log_cost(
            "infra", "local_compute", 0.002,
            detail="estimado_por_ciclo_10min",
        )
