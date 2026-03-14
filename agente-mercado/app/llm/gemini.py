"""Implementación Gemini 3.1 Pro Preview — cliente LLM principal con fallback automático."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time

import httpx

from app.config import settings
from app.data.router import EnrichedMarket
from app.llm.base import LLMClient, ProbabilityEstimate
from app.llm.prompts import (
    CRYPTO_ANALYSIS_SYSTEM,
    CRYPTO_ANALYSIS_USER,
)

log = logging.getLogger(__name__)

_SENSITIVE_FIELDS = {"api_key", "secret", "password", "private_key", "token"}


def _recover_partial_json(text: str) -> list[dict] | None:
    """Intenta recuperar objetos JSON completos de un array cortado por MAX_TOKENS."""
    text = text.strip()
    if not text.startswith("["):
        return None
    # Buscar el último '}' que cierra un objeto completo
    last_brace = text.rfind("}")
    if last_brace < 0:
        return None
    # Cerrar el array después del último objeto completo
    truncated = text[: last_brace + 1] + "]"
    try:
        parsed = json.loads(truncated)
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed
    except json.JSONDecodeError:
        pass
    return None


def _redact_log(text: str, max_len: int = 500) -> str:
    """Recorta y redacta datos sensibles de logs."""
    for field in _SENSITIVE_FIELDS:
        if field in text.lower():
            text = text.replace(text, "[REDACTED]")
    return text[:max_len] + ("..." if len(text) > max_len else "")


class GeminiClient(LLMClient):
    """Cliente para Gemini 3.1 Pro Preview con fallback automático a Flash."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=90.0)
        self._model = settings.gemini_model
        self._fallback_model = settings.gemini_fallback_model

    def _build_url(self, model: str) -> str:
        return f"{self.BASE_URL}/models/{model}:generateContent"

    async def estimate_fair_values(
        self,
        markets: list[EnrichedMarket],
        model_override: str | None = None,
        performance_context: str = "",
        system_prompt_override: str = "",
        user_prompt_override: str = "",
    ) -> list[ProbabilityEstimate]:
        """Envía un batch de mercados al LLM y parsea la respuesta.

        Args:
            markets: Lista de mercados enriquecidos para analizar.
            model_override: Modelo específico a usar (ignora el default).
            performance_context: Contexto de rendimiento historico para feedback.
            system_prompt_override: Prompt de sistema custom (para multi-estrategia).
            user_prompt_override: Template de prompt de usuario custom.
        """
        if not settings.gemini_api_key:
            log.error("GEMINI_API_KEY no configurada")
            return []

        # Construir datos de mercado para el prompt
        market_data_lines = []
        for m in markets:
            summary = m.data_summary
            market_data_lines.append(json.dumps(summary, ensure_ascii=False))
        market_data_text = "\n".join(market_data_lines)

        user_tpl = user_prompt_override or CRYPTO_ANALYSIS_USER
        user_prompt = user_tpl.format(
            count=len(markets), market_data=market_data_text
        )
        prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:16]

        system_prompt = system_prompt_override or CRYPTO_ANALYSIS_SYSTEM
        if performance_context:
            system_prompt = system_prompt + "\n\n" + performance_context

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "temperature": settings.gemini_temperature,
                "maxOutputTokens": settings.gemini_max_output_tokens,
                "responseMimeType": "application/json",
            },
        }

        start_time = time.monotonic()
        estimates: list[ProbabilityEstimate] = []
        current_model = model_override or self._model
        switched_to_fallback = False

        for attempt in range(4):  # 4 intentos: 2 con principal + 2 con fallback
            try:
                url = self._build_url(current_model)
                log.info(
                    "Llamando a Gemini modelo=%s (intento %d, hash=%s)",
                    current_model, attempt + 1, prompt_hash,
                )

                resp = await self._client.post(
                    url,
                    params={"key": settings.gemini_api_key},
                    json=payload,
                )

                if resp.status_code in (429, 503):
                    error_type = "Rate limited" if resp.status_code == 429 else "Servicio no disponible"
                    if not switched_to_fallback and current_model != self._fallback_model:
                        log.warning(
                            "%s (HTTP %d) con modelo principal %s. "
                            "Cambiando a fallback: %s",
                            error_type, resp.status_code,
                            current_model, self._fallback_model,
                        )
                        current_model = self._fallback_model
                        switched_to_fallback = True
                        await asyncio.sleep(2)
                        continue
                    else:
                        wait = 2 ** (attempt + 1)
                        log.warning(
                            "%s (HTTP %d) con %s, esperando %ds",
                            error_type, resp.status_code, current_model, wait,
                        )
                        await asyncio.sleep(wait)
                        continue

                resp.raise_for_status()
                elapsed = time.monotonic() - start_time

                response_data = resp.json()

                # Log de uso de tokens
                usage = response_data.get("usageMetadata", {})
                log.info(
                    "Gemini respondió en %.1fs | modelo=%s | tokens_in=%s tokens_out=%s | hash=%s",
                    elapsed,
                    current_model,
                    usage.get("promptTokenCount", "?"),
                    usage.get("candidatesTokenCount", "?"),
                    prompt_hash,
                )

                if switched_to_fallback:
                    log.info(
                        "Respuesta exitosa usando modelo fallback: %s",
                        current_model,
                    )

                # Extraer texto de la respuesta — múltiples formatos posibles
                candidates = response_data.get("candidates", [])
                if not candidates:
                    log.error("Gemini: sin candidates en respuesta")
                    return []

                candidate = candidates[0]
                finish_reason = candidate.get("finishReason", "UNKNOWN")
                log.info("Gemini finishReason=%s", finish_reason)

                # Gemini puede tener parts con thought=true (pensamiento
                # interno) y text parts (respuesta)
                all_parts = candidate.get("content", {}).get("parts", [])
                if not all_parts:
                    log.error(
                        "Gemini: sin parts. finishReason=%s, keys=%s",
                        finish_reason,
                        list(candidate.keys()),
                    )
                    log.error(
                        "Gemini candidate raw (800ch): %s",
                        json.dumps(candidate, ensure_ascii=False)[:800],
                    )
                    return []

                # Filtrar solo parts con texto de respuesta (no thinking)
                text_parts = [
                    p for p in all_parts
                    if "text" in p and not p.get("thought", False)
                ]
                if not text_parts:
                    # Si solo hay thinking parts, usar la última part con text
                    text_parts = [p for p in all_parts if "text" in p]

                if not text_parts:
                    log.error(
                        "Gemini: parts sin texto. parts=%s",
                        json.dumps(all_parts, ensure_ascii=False)[:500],
                    )
                    return []

                text = text_parts[0].get("text", "")

                # Debug: log primeros 300 chars de la respuesta
                log.info("Gemini raw (primeros 300): %s", text[:300].replace("\n", " "))

                # Intentar parsear — limpiar si tiene markdown wrappers
                clean_text = text.strip()
                if clean_text.startswith("```"):
                    # Remover ```json ... ```
                    lines = clean_text.split("\n")
                    clean_text = "\n".join(
                        l for l in lines if not l.strip().startswith("```")
                    )

                parsed = json.loads(clean_text)
                if not isinstance(parsed, list):
                    parsed = [parsed]

                for item in parsed:
                    direction = item.get("direction", "HOLD")
                    if direction == "HOLD":
                        continue  # No generar señal para HOLD

                    estimates.append(
                        ProbabilityEstimate(
                            symbol=item.get("symbol", ""),
                            direction=direction,
                            confidence=max(0.0, min(1.0, item.get("confidence", 0))),
                            deviation_pct=item.get("deviation_pct", 0),
                            take_profit_pct=max(0.005, item.get("take_profit_pct", 0.03)),
                            stop_loss_pct=max(0.005, item.get("stop_loss_pct", 0.02)),
                            rationale=item.get("rationale", ""),
                            data_sources=[r.provider for m2 in markets
                                          for r in m2.external_data if not r.error],
                        )
                    )

                return estimates

            except httpx.HTTPStatusError as e:
                log.error("Gemini HTTP error %d: %s", e.response.status_code,
                          _redact_log(e.response.text))
                if not switched_to_fallback and current_model != self._fallback_model:
                    log.warning(
                        "Error con modelo principal, cambiando a fallback: %s",
                        self._fallback_model,
                    )
                    current_model = self._fallback_model
                    switched_to_fallback = True
                    await asyncio.sleep(2)
                elif attempt < 3:
                    await asyncio.sleep(2 ** (attempt + 1))
            except json.JSONDecodeError:
                log.warning(
                    "Gemini JSON incompleto (hash=%s, finishReason posible=MAX_TOKENS)."
                    " Intentando recuperar items parciales...",
                    prompt_hash,
                )
                # Intentar recuperar JSON parcial cortado por MAX_TOKENS
                partial = _recover_partial_json(clean_text)
                if partial:
                    log.info("Recuperados %d items de JSON parcial", len(partial))
                    for item in partial:
                        direction = item.get("direction", "HOLD")
                        if direction == "HOLD":
                            continue
                        estimates.append(
                            ProbabilityEstimate(
                                symbol=item.get("symbol", ""),
                                direction=direction,
                                confidence=max(0.0, min(1.0, item.get("confidence", 0))),
                                deviation_pct=item.get("deviation_pct", 0),
                                take_profit_pct=max(0.005, item.get("take_profit_pct", 0.03)),
                                stop_loss_pct=max(0.005, item.get("stop_loss_pct", 0.02)),
                                rationale=item.get("rationale", ""),
                                data_sources=[r.provider for m2 in markets
                                              for r in m2.external_data if not r.error],
                            )
                        )
                    return estimates
                log.error("No se pudo recuperar nada del JSON parcial")
                return []
            except Exception:
                log.exception("Error inesperado llamando a Gemini (modelo=%s)", current_model)
                return []

        return estimates

    async def close(self) -> None:
        await self._client.aclose()
