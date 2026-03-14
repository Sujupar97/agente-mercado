"""Gestión de posiciones — scale-in, partial profits, trailing stop.

Implementa la filosofía de Oliver Vélez:
- "Perder 1 vela, ganar 2-12 velas"
- Añadir capital en pullbacks (scale-in)
- Tomar ganancias parciales en targets
- Trailing stop siguiendo la vela anterior
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentState, Trade

log = logging.getLogger(__name__)


@dataclass
class ScaleAction:
    """Acción de scale-in sugerida."""

    trade_id: int
    additional_size_usd: float
    reason: str


@dataclass
class PartialExit:
    """Acción de salida parcial sugerida."""

    trade_id: int
    exit_fraction: float  # 0.33 = cerrar 33% de la posición
    reason: str


class PositionScaler:
    """Gestiona scaling in/out de posiciones según Oliver Vélez.

    Reglas:
    - Scale-in: Si el trade va a favor y hace pullback al 50% → añadir 50% del tamaño original
    - Máximo 3 scale-ins por trade
    - Partial profit en 3 niveles: 33%, 33%, 34%
    - Trailing stop: mínimo/máximo de la vela anterior
    - Break-even: mover stop después del 1er partial
    """

    MAX_SCALE_INS = 3
    SCALE_IN_FRACTION = 0.50  # 50% del tamaño original
    PULLBACK_THRESHOLD = 0.50  # 50% de retroceso

    async def check_scale_in(
        self,
        trade: Trade,
        current_price: float,
        state: AgentState,
    ) -> ScaleAction | None:
        """Verifica si hay oportunidad de scale-in.

        Scale-in cuando el precio va a favor, retrocede al 50% del movimiento,
        y luego rebota. Indica que el movimiento va a continuar.
        """
        scale_ins = getattr(trade, "scale_ins", 0) or 0
        if scale_ins >= self.MAX_SCALE_INS:
            return None

        original_size = getattr(trade, "original_size_usd", None) or trade.size_usd
        additional = original_size * self.SCALE_IN_FRACTION

        # Verificar capital disponible
        if state.capital_usd < additional:
            return None

        entry = trade.entry_price
        if entry <= 0 or current_price <= 0:
            return None

        if trade.direction == "BUY":
            # El precio debe haber subido (ir a favor) y luego retrocedido
            # Necesitamos que el TP esté arriba → el precio intermedio
            tp = trade.take_profit_price or entry * 1.02
            max_move = tp - entry
            if max_move <= 0:
                return None

            # Pullback: el precio retrocedió al 50% del movimiento
            pullback_level = entry + max_move * self.PULLBACK_THRESHOLD
            if current_price <= pullback_level and current_price > entry:
                return ScaleAction(
                    trade_id=trade.id,
                    additional_size_usd=additional,
                    reason=f"Scale-in #{scale_ins + 1}: pullback a {self.PULLBACK_THRESHOLD:.0%} del movimiento",
                )

        elif trade.direction == "SELL":
            tp = trade.take_profit_price or entry * 0.98
            max_move = entry - tp
            if max_move <= 0:
                return None

            pullback_level = entry - max_move * self.PULLBACK_THRESHOLD
            if current_price >= pullback_level and current_price < entry:
                return ScaleAction(
                    trade_id=trade.id,
                    additional_size_usd=additional,
                    reason=f"Scale-in #{scale_ins + 1}: pullback a {self.PULLBACK_THRESHOLD:.0%} del movimiento",
                )

        return None

    def check_partial_profit(
        self,
        trade: Trade,
        current_price: float,
    ) -> PartialExit | None:
        """Verifica si toca tomar ganancia parcial.

        Niveles:
        - 1er partial (33%): cuando el precio gana 1x el riesgo
        - 2do partial (33%): cuando el precio gana 2x el riesgo
        - 3er partial (34%): trailing stop (no se cierra aquí, se deja correr)
        """
        partial_exits = getattr(trade, "partial_exits", 0) or 0
        if partial_exits >= 2:  # Solo 2 parciales, el 3ro es trailing
            return None

        entry = trade.entry_price
        initial_stop = getattr(trade, "initial_stop_price", None) or trade.stop_loss_price
        if not initial_stop or entry <= 0:
            return None

        risk = abs(entry - initial_stop)
        if risk <= 0:
            return None

        if trade.direction == "BUY":
            profit = current_price - entry
            profit_ratio = profit / risk if risk > 0 else 0

            if partial_exits == 0 and profit_ratio >= 1.0:
                return PartialExit(
                    trade_id=trade.id,
                    exit_fraction=0.33,
                    reason=f"1er partial: ganancia {profit_ratio:.1f}x riesgo",
                )
            elif partial_exits == 1 and profit_ratio >= 2.0:
                return PartialExit(
                    trade_id=trade.id,
                    exit_fraction=0.33,
                    reason=f"2do partial: ganancia {profit_ratio:.1f}x riesgo",
                )

        elif trade.direction == "SELL":
            profit = entry - current_price
            profit_ratio = profit / risk if risk > 0 else 0

            if partial_exits == 0 and profit_ratio >= 1.0:
                return PartialExit(
                    trade_id=trade.id,
                    exit_fraction=0.33,
                    reason=f"1er partial: ganancia {profit_ratio:.1f}x riesgo",
                )
            elif partial_exits == 1 and profit_ratio >= 2.0:
                return PartialExit(
                    trade_id=trade.id,
                    exit_fraction=0.33,
                    reason=f"2do partial: ganancia {profit_ratio:.1f}x riesgo",
                )

        return None

    def update_trailing_stop(
        self,
        trade: Trade,
        candles: list,
    ) -> float | None:
        """Calcula nuevo trailing stop basado en la vela anterior.

        Oliver Vélez: trailing stop = mínimo de la vela anterior (BUY)
        o máximo de la vela anterior (SELL). Solo se mueve a favor.
        """
        partial_exits = getattr(trade, "partial_exits", 0) or 0
        if partial_exits < 1:
            return None  # Solo trailing después del 1er partial

        if len(candles) < 2:
            return None

        prev_candle = candles[-2]  # Vela anterior a la actual
        current_trailing = getattr(trade, "trailing_stop_price", None)

        if trade.direction == "BUY":
            new_stop = prev_candle[3]  # Low de la vela anterior
            # Solo mover hacia arriba (a favor)
            if current_trailing and new_stop <= current_trailing:
                return None
            # No mover por debajo del entry (ya estamos en profit)
            if new_stop < trade.entry_price:
                new_stop = trade.entry_price
            return new_stop

        elif trade.direction == "SELL":
            new_stop = prev_candle[2]  # High de la vela anterior
            if current_trailing and new_stop >= current_trailing:
                return None
            if new_stop > trade.entry_price:
                new_stop = trade.entry_price
            return new_stop

        return None

    def should_move_to_breakeven(self, trade: Trade) -> bool:
        """Verifica si se debe mover el stop a break-even.

        Se mueve a BE después del primer partial profit.
        """
        partial_exits = getattr(trade, "partial_exits", 0) or 0
        if partial_exits < 1:
            return False

        current_stop = trade.stop_loss_price
        entry = trade.entry_price

        if trade.direction == "BUY":
            return current_stop is not None and current_stop < entry
        elif trade.direction == "SELL":
            return current_stop is not None and current_stop > entry

        return False
