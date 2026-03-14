"""Tracker de posiciones — TP/SL, trailing stops, partial profits, ciclo de mejora."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import ccxt.async_support as ccxt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentState, Bitacora, Signal, SignalOutcome, Trade
from app.learning.improvement_engine import ImprovementEngine
from app.trading.executor import OrderExecutor
from app.trading.position_scaler import PositionScaler

log = logging.getLogger(__name__)


class PositionTracker:
    """Monitorea posiciones abiertas: TP/SL, trailing stops, partial profits."""

    def __init__(self, session: AsyncSession, executor: OrderExecutor) -> None:
        self._session = session
        self._executor = executor
        self._scaler = PositionScaler()
        self._public_exchange: ccxt.Exchange | None = None

    async def _get_exchange(self) -> ccxt.Exchange | None:
        """Obtiene exchange: usa el del executor, o crea uno público para simulación."""
        if self._executor._exchange:
            return self._executor._exchange
        if self._public_exchange is None:
            self._public_exchange = ccxt.binance({"enableRateLimit": True})
        return self._public_exchange

    async def check_open_positions(self) -> int:
        """Verifica todas las posiciones abiertas contra precios actuales.

        Returns:
            Número de posiciones cerradas en esta verificación.
        """
        result = await self._session.execute(
            select(Trade).where(Trade.status == "OPEN")
        )
        open_trades = result.scalars().all()
        if not open_trades:
            return 0

        closed_count = 0
        exchange = await self._get_exchange()
        if not exchange:
            log.warning("No exchange disponible para verificar posiciones")
            return 0

        for trade in open_trades:
            try:
                ticker = await exchange.fetch_ticker(trade.symbol)
                current_price = ticker.get("last", 0)
                if current_price <= 0:
                    continue

                strategy_id = trade.strategy_id or "oliver_elephant"

                # 1. Verificar partial profit (antes de TP/SL)
                partial = self._scaler.check_partial_profit(trade, current_price)
                if partial and trade.is_simulation:
                    await self._execute_partial_profit(
                        trade, current_price, partial.exit_fraction, strategy_id,
                    )

                # 2. Determinar stop efectivo (trailing > normal)
                trailing = getattr(trade, "trailing_stop_price", None)
                effective_stop = trailing or trade.stop_loss_price

                # 3. Verificar TP/SL
                should_close = False
                exit_reason = ""

                if trade.direction == "BUY":
                    if trade.take_profit_price and current_price >= trade.take_profit_price:
                        should_close = True
                        exit_reason = "TAKE_PROFIT"
                    elif effective_stop and current_price <= effective_stop:
                        should_close = True
                        exit_reason = "TRAILING_STOP" if trailing else "STOP_LOSS"
                elif trade.direction == "SELL":
                    if trade.take_profit_price and current_price <= trade.take_profit_price:
                        should_close = True
                        exit_reason = "TAKE_PROFIT"
                    elif effective_stop and current_price >= effective_stop:
                        should_close = True
                        exit_reason = "TRAILING_STOP" if trailing else "STOP_LOSS"

                if should_close:
                    closed = await self._close_trade(
                        trade, current_price, exit_reason, strategy_id,
                    )
                    if closed:
                        closed_count += 1

            except Exception:
                log.exception("Error verificando posición %s %s", trade.symbol, trade.direction)

        if closed_count > 0:
            await self._session.commit()

        # Reconciliar contador de posiciones con la realidad
        await self._reconcile_position_counts()

        # Cerrar exchange público si lo creamos
        if self._public_exchange:
            await self._public_exchange.close()
            self._public_exchange = None

        return closed_count

    async def _execute_partial_profit(
        self,
        trade: Trade,
        current_price: float,
        fraction: float,
        strategy_id: str,
    ) -> None:
        """Ejecuta una salida parcial en simulación."""
        qty_to_close = (trade.quantity or 0) * fraction
        size_to_close = trade.size_usd * fraction

        if trade.direction == "BUY":
            partial_pnl = (current_price - trade.entry_price) * qty_to_close
        else:
            partial_pnl = (trade.entry_price - current_price) * qty_to_close
        partial_pnl -= (trade.fees or 0) * fraction

        # Reducir tamaño del trade
        trade.quantity = (trade.quantity or 0) - qty_to_close
        trade.size_usd -= size_to_close
        trade.partial_exits = (getattr(trade, "partial_exits", 0) or 0) + 1

        # Mover stop a break-even si corresponde
        if self._scaler.should_move_to_breakeven(trade):
            trade.stop_loss_price = trade.entry_price
            log.info(
                "[%s] Stop movido a break-even $%.4f",
                strategy_id, trade.entry_price,
            )

        # Devolver capital parcial + ganancia
        await self._session.execute(
            update(AgentState)
            .where(AgentState.strategy_id == strategy_id)
            .values(
                capital_usd=AgentState.capital_usd + partial_pnl + size_to_close,
                total_pnl=AgentState.total_pnl + partial_pnl,
            )
        )

        log.info(
            "[%s] Partial #%d: %s %s | cerrado %.0f%% @ $%.4f | P&L=$%.4f",
            strategy_id, trade.partial_exits,
            trade.direction, trade.symbol,
            fraction * 100, current_price, partial_pnl,
        )

    async def _close_trade(
        self,
        trade: Trade,
        current_price: float,
        exit_reason: str,
        strategy_id: str,
    ) -> bool:
        """Cierra un trade completamente (simulación o live)."""
        if trade.is_simulation:
            if trade.direction == "BUY":
                pnl = (current_price - trade.entry_price) * (trade.quantity or 0)
            else:
                pnl = (trade.entry_price - current_price) * (trade.quantity or 0)
            pnl -= trade.fees or 0

            trade.exit_price = current_price
            trade.pnl = pnl
            trade.status = "CLOSED"
            trade.closed_at = datetime.now(timezone.utc)

            await self._update_agent_state(pnl, trade.size_usd, strategy_id)
            await self._record_signal_outcome(trade, pnl, exit_reason)
            await self._update_bitacora(trade, exit_reason, current_price, pnl)
            await self._register_improvement_trade(trade)

            log.info(
                "[%s] SIM Cerrada (%s): %s %s | entrada=$%.4f salida=$%.4f | P&L=$%.4f",
                strategy_id, exit_reason, trade.direction, trade.symbol,
                trade.entry_price, current_price, pnl,
            )
            return True
        else:
            # Live: cerrar vía exchange
            close_result = await self._executor.close_position(
                symbol=trade.symbol,
                direction=trade.direction,
                quantity=trade.quantity,
            )

            if close_result.success:
                if trade.direction == "BUY":
                    pnl = (current_price - trade.entry_price) * trade.quantity
                else:
                    pnl = (trade.entry_price - current_price) * trade.quantity
                pnl -= trade.fees or 0

                trade.exit_price = current_price
                trade.pnl = pnl
                trade.status = "CLOSED"
                trade.closed_at = datetime.now(timezone.utc)

                await self._update_agent_state(pnl, trade.size_usd, strategy_id)
                await self._record_signal_outcome(trade, pnl, exit_reason)
                await self._update_bitacora(trade, exit_reason, current_price, pnl)
                await self._register_improvement_trade(trade)

                log.info(
                    "[%s] Posición cerrada (%s): %s %s | entrada=$%.4f salida=$%.4f | P&L=$%.4f",
                    strategy_id, exit_reason, trade.direction, trade.symbol,
                    trade.entry_price, current_price, pnl,
                )
                return True

        return False

    async def _register_improvement_trade(self, trade: Trade) -> None:
        """Registra un trade cerrado en el ciclo de mejora de 20 trades."""
        try:
            engine = ImprovementEngine(self._session)
            ready = await engine.record_trade(trade)
            if ready:
                log.info(
                    "[%s] Ciclo de mejora alcanzó umbral — listo para análisis LLM",
                    trade.strategy_id,
                )
        except Exception:
            log.debug("Error registrando trade en ciclo de mejora (no crítico)")

    async def _record_signal_outcome(
        self, trade: Trade, pnl: float, exit_reason: str,
    ) -> None:
        """Registra el resultado real de la señal para el sistema de aprendizaje."""
        if not trade.signal_id:
            return

        signal_result = await self._session.execute(
            select(Signal).where(Signal.id == trade.signal_id)
        )
        signal = signal_result.scalar_one_or_none()
        if not signal:
            return

        closed_at = trade.closed_at or datetime.now(timezone.utc)
        hold_minutes = (closed_at - trade.created_at).total_seconds() / 60

        outcome = SignalOutcome(
            signal_id=signal.id,
            trade_id=trade.id,
            symbol=trade.symbol,
            direction=trade.direction,
            strategy_id=trade.strategy_id or "oliver_elephant",
            predicted_confidence=signal.confidence,
            predicted_deviation=signal.deviation_pct,
            predicted_tp_pct=signal.take_profit_pct,
            predicted_sl_pct=signal.stop_loss_pct,
            actual_pnl=pnl,
            actual_return_pct=pnl / trade.size_usd if trade.size_usd > 0 else 0,
            hit_tp=(exit_reason == "TAKE_PROFIT"),
            hold_duration_minutes=hold_minutes,
            llm_model=signal.llm_model,
            hour_of_day=trade.created_at.hour,
            day_of_week=trade.created_at.weekday(),
        )
        self._session.add(outcome)

    async def _update_bitacora(
        self, trade: Trade, exit_reason: str, exit_price: float, pnl: float,
    ) -> None:
        """Actualiza la bitácora al cerrar un trade."""
        result = await self._session.execute(
            select(Bitacora).where(Bitacora.trade_id == trade.id)
        )
        bitacora = result.scalar_one_or_none()
        if not bitacora:
            return

        closed_at = trade.closed_at or datetime.now(timezone.utc)
        hold_minutes = (closed_at - trade.created_at).total_seconds() / 60

        bitacora.exit_reason = exit_reason
        bitacora.exit_price = exit_price
        bitacora.exit_time = closed_at
        bitacora.pnl = pnl
        bitacora.hold_duration_minutes = hold_minutes

    async def _reconcile_position_counts(self) -> None:
        """Corrige positions_open por estrategia si no coincide con la realidad."""
        result = await self._session.execute(
            select(Trade.strategy_id, func.count(Trade.id))
            .where(Trade.status == "OPEN")
            .group_by(Trade.strategy_id)
        )
        real_counts: dict[str, int] = {}
        for row in result.all():
            real_counts[row[0]] = row[1]

        states_result = await self._session.execute(select(AgentState))
        states = states_result.scalars().all()

        for state in states:
            sid = state.strategy_id
            actual = real_counts.get(sid, 0)
            if state.positions_open != actual:
                log.warning(
                    "[%s] Reconciliación: contador=%d, real=%d — corrigiendo",
                    sid, state.positions_open, actual,
                )
                state.positions_open = actual

        await self._session.commit()

    async def _update_agent_state(
        self, pnl: float, size_usd: float, strategy_id: str = "oliver_elephant",
    ) -> None:
        """Actualiza capital y estadísticas tras cerrar un trade."""
        await self._session.execute(
            update(AgentState)
            .where(AgentState.strategy_id == strategy_id)
            .values(
                capital_usd=AgentState.capital_usd + pnl + size_usd,
                total_pnl=AgentState.total_pnl + pnl,
                positions_open=AgentState.positions_open - 1,
                trades_won=AgentState.trades_won + (1 if pnl > 0 else 0),
                trades_lost=AgentState.trades_lost + (1 if pnl <= 0 else 0),
            )
        )
        # Actualizar peak si es nuevo máximo
        state_result = await self._session.execute(
            select(AgentState).where(AgentState.strategy_id == strategy_id)
        )
        state = state_result.scalar_one_or_none()
        if state and state.capital_usd > state.peak_capital_usd:
            state.peak_capital_usd = state.capital_usd

    @staticmethod
    async def run_independent_check() -> int:
        """Ejecuta verificación de posiciones con su propia sesión DB."""
        from app.db.database import async_session_factory

        async with async_session_factory() as session:
            executor = OrderExecutor()
            tracker = PositionTracker(session, executor)
            try:
                closed = await tracker.check_open_positions()
                if closed > 0:
                    log.info("Tracker rápido: %d posiciones cerradas", closed)
                return closed
            except Exception:
                log.exception("Error en tracker rápido de posiciones")
                await session.rollback()
                return 0
