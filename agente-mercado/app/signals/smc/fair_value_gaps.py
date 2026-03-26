"""Detector de Fair Value Gaps (FVG) — imbalances de precio.

Un FVG es un gap en el precio creado por un movimiento impulsivo fuerte.
Se forma cuando hay un hueco entre el high de vela 1 y el low de vela 3
(en un impulso alcista) o entre el low de vela 1 y el high de vela 3
(en un impulso bajista).

El precio tiende a regresar a llenar estos gaps antes de continuar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.broker.models import Candle

log = logging.getLogger(__name__)


@dataclass
class FairValueGap:
    """Un gap de valor justo (imbalance)."""

    type: str  # "BULLISH_FVG" | "BEARISH_FVG"
    high: float  # Techo del gap
    low: float  # Piso del gap
    index: int  # Índice de la vela del medio (vela 2)
    is_filled: bool = False  # True si el precio llenó el gap

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2

    @property
    def size(self) -> float:
        return self.high - self.low


class FVGDetector:
    """Detecta Fair Value Gaps en los datos de precio."""

    def __init__(self, min_gap_atr_mult: float = 0.2) -> None:
        """
        Args:
            min_gap_atr_mult: Tamaño mínimo del gap como múltiplo de ATR.
                              Gaps más pequeños se ignoran como ruido.
        """
        self._min_gap_mult = min_gap_atr_mult

    def find_gaps(
        self, candles: list[Candle], atr: float = 0.0,
    ) -> list[FairValueGap]:
        """Encuentra todos los FVGs en las velas.

        Args:
            candles: Lista de velas OHLCV
            atr: ATR actual para filtrar gaps demasiado pequeños

        Returns:
            Lista de FairValueGap detectados
        """
        if len(candles) < 3:
            return []

        gaps: list[FairValueGap] = []
        min_size = atr * self._min_gap_mult if atr > 0 else 0

        for i in range(1, len(candles) - 1):
            c1 = candles[i - 1]  # Vela 1
            c3 = candles[i + 1]  # Vela 3

            # Bullish FVG: gap entre high de vela 1 y low de vela 3
            if c3.low > c1.high:
                gap_size = c3.low - c1.high
                if gap_size >= min_size:
                    gaps.append(FairValueGap(
                        type="BULLISH_FVG",
                        high=c3.low,
                        low=c1.high,
                        index=i,
                    ))

            # Bearish FVG: gap entre low de vela 1 y high de vela 3
            if c3.high < c1.low:
                gap_size = c1.low - c3.high
                if gap_size >= min_size:
                    gaps.append(FairValueGap(
                        type="BEARISH_FVG",
                        high=c1.low,
                        low=c3.high,
                        index=i,
                    ))

        # Marcar gaps llenados
        self._check_fill_status(candles, gaps)
        return gaps

    @staticmethod
    def _check_fill_status(candles: list[Candle], gaps: list[FairValueGap]) -> None:
        """Verifica si cada gap ha sido llenado por velas posteriores."""
        for gap in gaps:
            for i in range(gap.index + 2, len(candles)):
                c = candles[i]
                if gap.type == "BULLISH_FVG":
                    # El precio bajó y llenó el gap
                    if c.low <= gap.low:
                        gap.is_filled = True
                        break
                elif gap.type == "BEARISH_FVG":
                    # El precio subió y llenó el gap
                    if c.high >= gap.high:
                        gap.is_filled = True
                        break

    def get_unfilled_gaps(
        self, candles: list[Candle], atr: float = 0.0,
    ) -> list[FairValueGap]:
        """Retorna solo gaps que NO han sido llenados (todavía activos)."""
        all_gaps = self.find_gaps(candles, atr)
        return [g for g in all_gaps if not g.is_filled]
