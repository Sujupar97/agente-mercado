"""Pre-filtro técnico — selecciona pares con movimiento antes de enviar al LLM."""

from __future__ import annotations

import logging

from app.markets.base import MarketTicker

log = logging.getLogger(__name__)


class TechnicalPreFilter:
    """Filtra pares sin movimiento interesante para ahorrar llamadas al LLM."""

    @staticmethod
    def filter(tickers: list[MarketTicker], min_momentum: float = 0.5) -> list[MarketTicker]:
        """Selecciona pares con momentum y volumen relativo suficiente.

        Args:
            tickers: Lista de tickers viables (ya pasaron filtro de spread).
            min_momentum: Mínimo |cambio 24h %| para considerar un par.

        Returns:
            Lista filtrada y ordenada por magnitud de cambio (más volátil primero).
        """
        if not tickers:
            return []

        avg_volume = sum(t.volume_24h for t in tickers) / len(tickers)

        filtered = []
        for t in tickers:
            has_momentum = abs(t.change_24h_pct) > min_momentum
            has_volume = t.volume_24h >= avg_volume * 0.5
            if has_momentum and has_volume:
                filtered.append(t)

        # Ordenar por magnitud de cambio (más volátil primero)
        filtered.sort(key=lambda t: abs(t.change_24h_pct), reverse=True)

        log.info(
            "Pre-filtro técnico: %d/%d pares (momentum>%.1f%%, vol>=%.0f USD)",
            len(filtered), len(tickers), min_momentum, avg_volume * 0.5,
        )
        return filtered
