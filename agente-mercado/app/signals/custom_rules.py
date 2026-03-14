"""Motor de reglas configurables — para Andrés Valdez y futuras estrategias.

Las reglas se configuran via Strategy.params en BD (sin tocar código):
{
    "entry_rules": [
        {"type": "sma_cross", "fast": 10, "slow": 50, "direction": "above"},
        {"type": "rsi_range", "min": 30, "max": 70}
    ],
    "exit_rules": [
        {"type": "fixed_tp", "pct": 0.02},
        {"type": "fixed_sl", "pct": 0.01}
    ]
}

ESTADO: Placeholder — se implementará cuando el usuario proporcione las reglas.
"""

from __future__ import annotations

import logging

from app.signals.candle_patterns import SignalCandidate

log = logging.getLogger(__name__)


class CustomRuleEngine:
    """Motor de señales basado en reglas configurables por BD.

    Permite definir estrategias sin modificar código:
    las reglas de entrada/salida se almacenan como JSON en Strategy.params.
    """

    def __init__(self, params: dict) -> None:
        self._entry_rules = params.get("entry_rules", [])
        self._exit_rules = params.get("exit_rules", [])

    def generate_signals(
        self,
        symbols_data: dict[str, dict[str, list]],
    ) -> list[SignalCandidate]:
        """Genera señales según las reglas configuradas.

        TODO: Implementar cuando el usuario proporcione las reglas de Andrés Valdez.
        """
        log.debug("CustomRuleEngine: sin reglas configuradas todavía")
        return []
