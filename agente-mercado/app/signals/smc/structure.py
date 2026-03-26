"""Detector de estructura de mercado — HH/HL/LH/LL, BOS, ChoCH.

Principio Smart Money: El precio se mueve en estructura (swings).
- Tendencia alcista: Higher Highs + Higher Lows
- Tendencia bajista: Lower Highs + Lower Lows
- BOS (Break of Structure): confirma continuación de tendencia
- ChoCH (Change of Character): señala posible reversión
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.broker.models import Candle

log = logging.getLogger(__name__)

SWING_LOOKBACK = 3  # Velas a cada lado para confirmar swing


@dataclass
class StructurePoint:
    """Un punto de estructura (swing high o swing low)."""

    type: str  # "HH" | "HL" | "LH" | "LL" | "SH" | "SL" (initial)
    price: float
    index: int
    timestamp: datetime


@dataclass
class StructureBreak:
    """Ruptura de estructura — BOS o ChoCH."""

    type: str  # "BOS" | "ChoCH"
    direction: str  # "BULLISH" | "BEARISH"
    broken_level: float
    break_candle_index: int
    timestamp: datetime


class MarketStructureAnalyzer:
    """Analiza la estructura del mercado según Smart Money Concepts."""

    def __init__(self, swing_lookback: int = SWING_LOOKBACK) -> None:
        self._lookback = swing_lookback

    def identify_structure(self, candles: list[Candle]) -> list[StructurePoint]:
        """Identifica swing highs y swing lows, clasificados como HH/HL/LH/LL.

        Returns:
            Lista ordenada de StructurePoints
        """
        if len(candles) < self._lookback * 2 + 1:
            return []

        swings: list[StructurePoint] = []
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        for i in range(self._lookback, len(candles) - self._lookback):
            # Swing High: high[i] > todos los N vecinos
            is_swing_high = all(
                highs[i] > highs[i - j] and highs[i] > highs[i + j]
                for j in range(1, self._lookback + 1)
            )
            # Swing Low: low[i] < todos los N vecinos
            is_swing_low = all(
                lows[i] < lows[i - j] and lows[i] < lows[i + j]
                for j in range(1, self._lookback + 1)
            )

            if is_swing_high:
                swings.append(StructurePoint(
                    type="SH", price=highs[i],
                    index=i, timestamp=candles[i].timestamp,
                ))
            if is_swing_low:
                swings.append(StructurePoint(
                    type="SL", price=lows[i],
                    index=i, timestamp=candles[i].timestamp,
                ))

        # Clasificar como HH/HL/LH/LL comparando con el swing previo del mismo tipo
        self._classify_swings(swings)
        return swings

    def _classify_swings(self, swings: list[StructurePoint]) -> None:
        """Clasifica swings como HH/HL/LH/LL comparando consecutivos."""
        last_high: StructurePoint | None = None
        last_low: StructurePoint | None = None

        for sw in swings:
            if sw.type == "SH":
                if last_high is None:
                    sw.type = "SH"  # Primer swing, sin referencia
                elif sw.price > last_high.price:
                    sw.type = "HH"
                else:
                    sw.type = "LH"
                last_high = sw
            elif sw.type == "SL":
                if last_low is None:
                    sw.type = "SL"
                elif sw.price > last_low.price:
                    sw.type = "HL"
                else:
                    sw.type = "LL"
                last_low = sw

    def detect_breaks(
        self, candles: list[Candle], structure: list[StructurePoint],
    ) -> list[StructureBreak]:
        """Detecta BOS y ChoCH en la estructura.

        BOS = precio rompe swing en dirección de la tendencia actual.
        ChoCH = precio rompe swing en CONTRA de la tendencia actual.
        """
        if len(structure) < 3:
            return []

        breaks: list[StructureBreak] = []
        trend = self._current_trend(structure)

        # Buscar rupturas después del último swing
        last_sh = None
        last_sl = None
        for sw in structure:
            if sw.type in ("SH", "HH", "LH"):
                last_sh = sw
            elif sw.type in ("SL", "HL", "LL"):
                last_sl = sw

        if not last_sh or not last_sl:
            return breaks

        # Revisar velas después del último swing para detectar rupturas
        search_start = max(last_sh.index, last_sl.index) + 1
        for i in range(search_start, len(candles)):
            c = candles[i]

            # Rotura alcista: precio supera el último swing high
            if c.close > last_sh.price:
                break_type = "BOS" if trend == "BULLISH" else "ChoCH"
                breaks.append(StructureBreak(
                    type=break_type,
                    direction="BULLISH",
                    broken_level=last_sh.price,
                    break_candle_index=i,
                    timestamp=c.timestamp,
                ))
                break  # Solo el primer break

            # Rotura bajista: precio cae bajo el último swing low
            if c.close < last_sl.price:
                break_type = "BOS" if trend == "BEARISH" else "ChoCH"
                breaks.append(StructureBreak(
                    type=break_type,
                    direction="BEARISH",
                    broken_level=last_sl.price,
                    break_candle_index=i,
                    timestamp=c.timestamp,
                ))
                break

        return breaks

    def get_bias(self, candles: list[Candle]) -> str:
        """Determina el BIAS direccional basado en estructura.

        Returns: "BULLISH" | "BEARISH" | "NEUTRAL"
        """
        structure = self.identify_structure(candles)
        if len(structure) < 3:
            return "NEUTRAL"

        trend = self._current_trend(structure)

        # Verificar si hay ChoCH reciente que invalide la tendencia
        breaks = self.detect_breaks(candles, structure)
        for brk in breaks:
            if brk.type == "ChoCH":
                return brk.direction  # El ChoCH define el nuevo BIAS

        return trend

    @staticmethod
    def _current_trend(structure: list[StructurePoint]) -> str:
        """Determina tendencia actual por los últimos swings."""
        # Contar HH/HL vs LH/LL en los últimos 6 swings
        recent = structure[-6:]
        bullish = sum(1 for s in recent if s.type in ("HH", "HL"))
        bearish = sum(1 for s in recent if s.type in ("LH", "LL"))

        if bullish > bearish:
            return "BULLISH"
        elif bearish > bullish:
            return "BEARISH"
        return "NEUTRAL"
