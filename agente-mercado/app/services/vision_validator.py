"""Validador de entradas usando Claude Vision (POC).

Antes de ejecutar un trade S1/S2, renderiza el gráfico actual con entry/SL/TP
y le pregunta a Claude si la entrada se ve sólida visualmente.

Solo activo si `vision_validator_enabled = true` en settings.
Costo aproximado: ~$0.003 por validación (~$0.30/día con 100 trades).
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass

from app.broker.models import Candle
from app.config import settings
from app.services.chart_renderer import ChartLines, render_chart
from app.signals.rule_engine import ForexSignal

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Resultado del análisis visual."""

    valid: bool
    confidence: float  # 0-1
    reason: str

    @classmethod
    def fallback_approve(cls, reason: str) -> "ValidationResult":
        """Cuando el validador no puede correr, aprobar por defecto (no bloquear)."""
        return cls(valid=True, confidence=1.0, reason=f"Validator unavailable: {reason}")


class VisionValidator:
    """Cliente Claude Vision para validar entradas de trading."""

    _PROMPT_TEMPLATE = """Eres un trader profesional con 15 años de experiencia analizando gráficos.

Estás revisando una entrada que mi sistema automatizado quiere tomar en {instrument}:

- Estrategia: {strategy}
- Patrón detectado: {pattern}
- Dirección: {direction}
- Entry: {entry:.5f}
- Stop Loss: {stop_loss:.5f}
- Take Profit: {take_profit:.5f}
- R:R: 1:{rr:.1f}

En el gráfico ves las últimas ~60 velas. Líneas: AZUL=Entry, ROJO=SL, VERDE=TP, NARANJA=EMA20.

Evalúa SOLO en base a lo que ves visualmente:

1. ¿La estructura de precio respalda la dirección {direction}?
2. ¿Hay alguna trampa visual evidente (false breakout, divergencia, exhaustion)?
3. ¿El R:R se ve realista basado en estructura visible (resistencias/soportes)?
4. ¿La entrada se ve "limpia" o "sucia" (ej. está pegada a una resistencia que va a frenar el movimiento)?

Responde SOLO con JSON válido en este formato exacto, sin texto adicional:
{{"valid": true/false, "confidence": 0.0-1.0, "reason": "explicación breve en español, max 150 chars"}}
"""

    def __init__(self) -> None:
        self._client = None
        self._enabled = settings.vision_validator_enabled and bool(settings.anthropic_api_key)

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            except ImportError:
                log.error("anthropic SDK no instalado — vision validator deshabilitado")
                self._enabled = False
        return self._client

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def validate_entry(
        self,
        signal: ForexSignal,
        candles: list[Candle],
        strategy_name: str = "",
    ) -> ValidationResult:
        """Valida una entrada visualmente con Claude Vision.

        Si el validador está deshabilitado o falla, retorna fallback_approve
        (no bloquea trades cuando hay errores en el validador).
        """
        if not self._enabled:
            return ValidationResult.fallback_approve("disabled")

        client = self._get_client()
        if client is None:
            return ValidationResult.fallback_approve("no_client")

        # Render chart
        try:
            chart_png = render_chart(
                instrument=signal.instrument,
                candles=candles,
                lines=ChartLines(
                    entry=signal.entry_price,
                    stop_loss=signal.stop_price,
                    take_profit=signal.tp1_price,
                    direction=signal.direction,
                ),
                title_suffix=signal.pattern_type,
            )
        except Exception as e:
            log.exception("Error renderizando chart para validator")
            return ValidationResult.fallback_approve(f"render_error: {e}")

        # Build prompt
        prompt = self._PROMPT_TEMPLATE.format(
            instrument=signal.instrument,
            strategy=strategy_name or signal.strategy_id,
            pattern=signal.pattern_type,
            direction=signal.direction,
            entry=signal.entry_price,
            stop_loss=signal.stop_price,
            take_profit=signal.tp1_price,
            rr=signal.risk_reward_ratio,
        )

        # Call Claude Vision
        try:
            chart_b64 = base64.standard_b64encode(chart_png).decode("ascii")
            response = await client.messages.create(
                model=settings.anthropic_vision_model,
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": chart_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
        except Exception as e:
            log.exception("Error llamando Claude Vision")
            return ValidationResult.fallback_approve(f"api_error: {e}")

        # Parse response
        try:
            text = response.content[0].text if response.content else ""
            # Extract JSON from response (Claude may add markdown fences)
            match = re.search(r'\{.*?"valid".*?\}', text, re.DOTALL)
            if not match:
                log.warning("Vision validator: no JSON en respuesta: %s", text[:200])
                return ValidationResult.fallback_approve("no_json")

            data = json.loads(match.group(0))
            return ValidationResult(
                valid=bool(data.get("valid", True)),
                confidence=float(data.get("confidence", 0.5)),
                reason=str(data.get("reason", ""))[:200],
            )
        except Exception as e:
            log.exception("Error parseando respuesta del validator")
            return ValidationResult.fallback_approve(f"parse_error: {e}")
