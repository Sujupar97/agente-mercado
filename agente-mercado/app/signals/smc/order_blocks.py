"""Detector de Order Blocks — zonas de acumulación institucional.

Un Order Block es la última vela contraria antes de un movimiento impulsivo
que rompe estructura (BOS). Las instituciones colocan órdenes masivas aquí,
y el precio tiende a regresar a estas zonas antes de continuar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.broker.models import Candle
from app.signals.smc.structure import StructureBreak

log = logging.getLogger(__name__)


@dataclass
class OrderBlock:
    """Zona de Order Block identificada."""

    type: str  # "BULLISH_OB" | "BEARISH_OB"
    high: float
    low: float
    midpoint: float  # 50% del OB — entrada conservadora
    origin_index: int
    origin_candle: Candle
    is_mitigated: bool = False  # True si el precio ya volvió

    @property
    def range(self) -> float:
        return self.high - self.low


class OrderBlockDetector:
    """Detecta Order Blocks basados en rupturas de estructura."""

    def __init__(self, max_ob_age: int = 50) -> None:
        """
        Args:
            max_ob_age: Máximo de velas hacia atrás para buscar el OB desde el BOS.
        """
        self._max_ob_age = max_ob_age

    def find_order_blocks(
        self,
        candles: list[Candle],
        structure_breaks: list[StructureBreak],
    ) -> list[OrderBlock]:
        """Encuentra Order Blocks asociados a rupturas de estructura.

        Para cada BOS/ChoCH, busca la última vela contraria antes del impulso.
        """
        order_blocks: list[OrderBlock] = []

        for brk in structure_breaks:
            ob = self._find_ob_for_break(candles, brk)
            if ob:
                # Verificar si ya fue mitigado (precio regresó al OB)
                ob.is_mitigated = self._check_mitigation(candles, ob, brk.break_candle_index)
                order_blocks.append(ob)

        return order_blocks

    def _find_ob_for_break(
        self, candles: list[Candle], brk: StructureBreak,
    ) -> OrderBlock | None:
        """Encuentra el OB para una ruptura de estructura específica.

        Bullish OB: última vela BAJISTA antes del impulso alcista.
        Bearish OB: última vela ALCISTA antes del impulso bajista.
        """
        break_idx = brk.break_candle_index
        search_start = max(0, break_idx - self._max_ob_age)

        if brk.direction == "BULLISH":
            # Buscar última vela bajista antes del impulso
            for i in range(break_idx - 1, search_start - 1, -1):
                c = candles[i]
                if c.close < c.open:  # Vela bajista
                    return OrderBlock(
                        type="BULLISH_OB",
                        high=c.high,
                        low=c.low,
                        midpoint=(c.high + c.low) / 2,
                        origin_index=i,
                        origin_candle=c,
                    )

        elif brk.direction == "BEARISH":
            # Buscar última vela alcista antes del impulso
            for i in range(break_idx - 1, search_start - 1, -1):
                c = candles[i]
                if c.close > c.open:  # Vela alcista
                    return OrderBlock(
                        type="BEARISH_OB",
                        high=c.high,
                        low=c.low,
                        midpoint=(c.high + c.low) / 2,
                        origin_index=i,
                        origin_candle=c,
                    )

        return None

    @staticmethod
    def _check_mitigation(
        candles: list[Candle], ob: OrderBlock, from_index: int,
    ) -> bool:
        """Verifica si el precio ya regresó al OB (mitigado)."""
        for i in range(from_index, len(candles)):
            c = candles[i]
            if ob.type == "BULLISH_OB":
                # El precio bajó hasta el OB
                if c.low <= ob.high:
                    return True
            elif ob.type == "BEARISH_OB":
                # El precio subió hasta el OB
                if c.high >= ob.low:
                    return True
        return False

    def get_active_order_blocks(
        self,
        candles: list[Candle],
        structure_breaks: list[StructureBreak],
    ) -> list[OrderBlock]:
        """Retorna solo OBs que NO han sido mitigados (todavía activos)."""
        all_obs = self.find_order_blocks(candles, structure_breaks)
        return [ob for ob in all_obs if not ob.is_mitigated]
