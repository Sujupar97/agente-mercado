"""Máquina de estados del agente — LIVE / SIMULATION / PAUSED / SHUTDOWN."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AgentState, Trade
from app.pnl.calculator import PnLCalculator

log = logging.getLogger(__name__)


@dataclass
class SurvivalCheck:
    """Resultado de la evaluación 'paga por ti mismo o muere'."""

    action: str  # "CONTINUE" | "WARNING" | "SIMULATION" | "SHUTDOWN"
    reason: str
    net_7d: float = 0.0
    net_14d: float = 0.0


class StateManager:
    """Gestiona el estado y las transiciones del agente."""

    def __init__(
        self, session: AsyncSession, strategy_id: str = "momentum",
    ) -> None:
        self._session = session
        self._strategy_id = strategy_id

    async def get_state(self) -> AgentState | None:
        result = await self._session.execute(
            select(AgentState).where(AgentState.strategy_id == self._strategy_id)
        )
        return result.scalar_one_or_none()

    async def ensure_state(self) -> AgentState:
        """Garantiza que existe un estado inicial."""
        state = await self.get_state()
        if not state:
            state = AgentState(
                strategy_id=self._strategy_id,
                mode=settings.agent_mode,
                capital_usd=settings.initial_capital_usd,
                peak_capital_usd=settings.initial_capital_usd,
            )
            self._session.add(state)
            await self._session.commit()
            log.info("Estado inicial creado: strategy=%s, modo=%s, capital=$%.2f",
                     self._strategy_id, state.mode, state.capital_usd)
        return state

    async def set_mode(self, mode: str) -> None:
        """Cambia el modo del agente."""
        old_state = await self.get_state()
        old_mode = old_state.mode if old_state else "UNKNOWN"
        await self._session.execute(
            update(AgentState)
            .where(AgentState.strategy_id == self._strategy_id)
            .values(mode=mode)
        )
        await self._session.commit()
        log.warning("[%s] Modo del agente: %s → %s", self._strategy_id, old_mode, mode)

    async def update_cycle_stats(
        self, markets_scanned: int, trades_executed: int
    ) -> None:
        """Actualiza estadísticas tras un ciclo."""
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(AgentState)
            .where(AgentState.strategy_id == self._strategy_id)
            .values(
                markets_scanned_total=AgentState.markets_scanned_total + markets_scanned,
                trades_executed_total=AgentState.trades_executed_total + trades_executed,
                last_cycle_at=now,
                last_trade_at=now if trades_executed > 0 else AgentState.last_trade_at,
            )
        )

    async def evaluate_survival(self) -> SurvivalCheck:
        """Evalúa la condición 'paga por ti mismo o muere'.

        En modo SIMULATION, NUNCA retorna SHUTDOWN — el agente debe seguir
        operando para generar datos de aprendizaje.
        """
        state = await self.get_state()
        if not state:
            return SurvivalCheck(action="SHUTDOWN", reason="No state found")

        is_simulation = state.mode == "SIMULATION"

        # 1. Capital agotado
        if state.capital_usd <= 0:
            if is_simulation:
                log.warning(
                    "[%s] SIMULATION: Capital agotado ($%.2f) — continuando para aprendizaje",
                    self._strategy_id, state.capital_usd,
                )
                return SurvivalCheck(
                    action="WARNING",
                    reason=f"Capital simulado agotado: ${state.capital_usd:.2f}",
                )
            return SurvivalCheck(
                action="SHUTDOWN",
                reason=f"Capital agotado: ${state.capital_usd:.2f}",
            )

        # 2. Drawdown máximo (basado en equity = cash + posiciones)
        if state.peak_capital_usd > 0:
            positions_result = await self._session.execute(
                select(func.coalesce(func.sum(Trade.size_usd), 0.0))
                .where(
                    Trade.status == "OPEN",
                    Trade.strategy_id == self._strategy_id,
                )
            )
            capital_in_positions = float(positions_result.scalar() or 0.0)
            equity = state.capital_usd + capital_in_positions
            drawdown = (state.peak_capital_usd - equity) / state.peak_capital_usd
            if drawdown >= settings.max_drawdown_pct:
                if is_simulation:
                    log.warning(
                        "[%s] SIMULATION: Drawdown %.1f%% >= limite %.1f%% — continuando",
                        self._strategy_id, drawdown * 100, settings.max_drawdown_pct * 100,
                    )
                    return SurvivalCheck(
                        action="WARNING",
                        reason=f"Drawdown simulado {drawdown:.1%} >= {settings.max_drawdown_pct:.1%}",
                    )
                return SurvivalCheck(
                    action="SIMULATION",
                    reason=f"Drawdown {drawdown:.1%} >= {settings.max_drawdown_pct:.1%}",
                )

        # 3. Ventana de 14 días: beneficio neto
        pnl_calc = PnLCalculator(self._session)
        net_14d = await pnl_calc.get_net_profit(days=settings.survival_shutdown_days)
        net_7d = await pnl_calc.get_net_profit(days=settings.survival_warning_days)

        if net_14d < 0:
            if is_simulation:
                return SurvivalCheck(
                    action="WARNING",
                    reason=f"Net 14d simulado: ${net_14d:.2f}",
                    net_7d=net_7d,
                    net_14d=net_14d,
                )
            return SurvivalCheck(
                action="SIMULATION",
                reason=f"Net 14d: ${net_14d:.2f} (no cubre costos)",
                net_7d=net_7d,
                net_14d=net_14d,
            )

        if net_7d < 0:
            return SurvivalCheck(
                action="WARNING",
                reason=f"Net 7d: ${net_7d:.2f} (tendencia negativa)",
                net_7d=net_7d,
                net_14d=net_14d,
            )

        return SurvivalCheck(
            action="CONTINUE",
            reason="Rentable",
            net_7d=net_7d,
            net_14d=net_14d,
        )
