"""Detector de Liquidity — pools de liquidez y sweeps.

Las instituciones necesitan liquidez para ejecutar órdenes grandes.
La liquidez se acumula en:
- Equal highs/lows (niveles repetidos donde muchos traders ponen stops)
- Swing highs/lows previos (stops de breakout traders)

Un Liquidity Sweep ocurre cuando el precio barre estos niveles brevemente
para ejecutar órdenes institucionales, y luego revierte.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.broker.models import Candle
from app.signals.smc.structure import StructurePoint

log = logging.getLogger(__name__)

EQUAL_LEVEL_TOLERANCE_ATR = 0.15  # Niveles se consideran "iguales" si están a < 0.15 ATR


@dataclass
class LiquidityPool:
    """Zona de acumulación de liquidez."""

    type: str  # "BUY_SIDE" (above price) | "SELL_SIDE" (below price)
    level: float
    touches: int  # Cuántas veces el precio tocó este nivel
    last_touch_index: int


@dataclass
class LiquiditySweep:
    """Barrido de liquidez detectado."""

    type: str  # "BUY_SIDE_SWEEP" | "SELL_SIDE_SWEEP"
    swept_level: float
    sweep_candle_index: int
    wick_size: float  # Tamaño de la mecha que barrió


class LiquidityDetector:
    """Detecta pools de liquidez y sweeps."""

    def __init__(self, tolerance_atr: float = EQUAL_LEVEL_TOLERANCE_ATR) -> None:
        self._tolerance_atr = tolerance_atr

    def find_liquidity_pools(
        self,
        candles: list[Candle],
        structure: list[StructurePoint],
        atr: float,
    ) -> list[LiquidityPool]:
        """Identifica zonas de liquidez basadas en swing points y equal levels.

        Args:
            candles: Datos de precio
            structure: Puntos de estructura (swings)
            atr: ATR actual para calcular tolerancia
        """
        pools: list[LiquidityPool] = []
        tolerance = atr * self._tolerance_atr

        # 1. Swing highs como buy-side liquidity
        swing_highs = [s for s in structure if s.type in ("SH", "HH", "LH")]
        for sh in swing_highs:
            pools.append(LiquidityPool(
                type="BUY_SIDE",
                level=sh.price,
                touches=1,
                last_touch_index=sh.index,
            ))

        # 2. Swing lows como sell-side liquidity
        swing_lows = [s for s in structure if s.type in ("SL", "HL", "LL")]
        for sl in swing_lows:
            pools.append(LiquidityPool(
                type="SELL_SIDE",
                level=sl.price,
                touches=1,
                last_touch_index=sl.index,
            ))

        # 3. Detectar equal highs/lows (múltiples toques al mismo nivel)
        pools = self._merge_equal_levels(pools, tolerance)

        return pools

    def detect_sweeps(
        self,
        candles: list[Candle],
        pools: list[LiquidityPool],
        lookback: int = 10,
    ) -> list[LiquiditySweep]:
        """Detecta sweeps de liquidez en las últimas N velas.

        Un sweep es cuando el precio rompe brevemente un nivel de liquidez
        con una mecha, pero cierra de vuelta (señal de reversa).
        """
        sweeps: list[LiquiditySweep] = []
        search_start = max(0, len(candles) - lookback)

        for i in range(search_start, len(candles)):
            c = candles[i]

            for pool in pools:
                if pool.last_touch_index >= i:
                    continue  # El pool es posterior a esta vela

                if pool.type == "BUY_SIDE":
                    # Buy-side sweep: high supera el nivel pero close queda abajo
                    if c.high > pool.level and c.close < pool.level:
                        wick = c.high - max(c.open, c.close)
                        sweeps.append(LiquiditySweep(
                            type="BUY_SIDE_SWEEP",
                            swept_level=pool.level,
                            sweep_candle_index=i,
                            wick_size=wick,
                        ))

                elif pool.type == "SELL_SIDE":
                    # Sell-side sweep: low rompe el nivel pero close queda arriba
                    if c.low < pool.level and c.close > pool.level:
                        wick = min(c.open, c.close) - c.low
                        sweeps.append(LiquiditySweep(
                            type="SELL_SIDE_SWEEP",
                            swept_level=pool.level,
                            sweep_candle_index=i,
                            wick_size=wick,
                        ))

        return sweeps

    @staticmethod
    def _merge_equal_levels(
        pools: list[LiquidityPool], tolerance: float,
    ) -> list[LiquidityPool]:
        """Agrupa niveles cercanos como equal highs/lows."""
        if not pools:
            return pools

        merged: list[LiquidityPool] = []
        sorted_pools = sorted(pools, key=lambda p: p.level)

        current = sorted_pools[0]
        for pool in sorted_pools[1:]:
            if abs(pool.level - current.level) <= tolerance and pool.type == current.type:
                # Merge: acumular toques
                current = LiquidityPool(
                    type=current.type,
                    level=(current.level + pool.level) / 2,  # Promedio
                    touches=current.touches + pool.touches,
                    last_touch_index=max(current.last_touch_index, pool.last_touch_index),
                )
            else:
                merged.append(current)
                current = pool

        merged.append(current)
        return merged
