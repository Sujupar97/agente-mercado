"""Calculador de P&L — realizado + no realizado."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentState, CostLog, Trade

log = logging.getLogger(__name__)


class PnLCalculator:
    """Calcula P&L neto del agente."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_total_pnl(self) -> float:
        """P&L total de trades cerrados."""
        result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
                Trade.status == "CLOSED"
            )
        )
        return result.scalar_one() or 0.0

    async def get_pnl_window(self, days: int) -> float:
        """P&L en una ventana móvil de N días."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
                Trade.status == "CLOSED",
                Trade.closed_at >= since,
            )
        )
        return result.scalar_one() or 0.0

    async def get_total_costs(self) -> float:
        """Costos totales acumulados."""
        result = await self._session.execute(
            select(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
        )
        return result.scalar_one() or 0.0

    async def get_costs_window(self, days: int) -> float:
        """Costos en una ventana móvil de N días."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(func.coalesce(func.sum(CostLog.amount_usd), 0.0)).where(
                CostLog.created_at >= since
            )
        )
        return result.scalar_one() or 0.0

    async def get_net_profit(self, days: int | None = None) -> float:
        """Beneficio neto = P&L - costos."""
        if days:
            pnl = await self.get_pnl_window(days)
            costs = await self.get_costs_window(days)
        else:
            pnl = await self.get_total_pnl()
            costs = await self.get_total_costs()
        return pnl - costs

    async def get_win_rate(self) -> float:
        """Porcentaje de trades ganadores."""
        result = await self._session.execute(
            select(AgentState).where(AgentState.strategy_id == "momentum")
        )
        state = result.scalar_one_or_none()
        if not state:
            return 0.0
        total = state.trades_won + state.trades_lost
        if total == 0:
            return 0.0
        return state.trades_won / total

    async def get_summary(self) -> dict:
        """Resumen completo de P&L."""
        state_result = await self._session.execute(
            select(AgentState).where(AgentState.strategy_id == "momentum")
        )
        state = state_result.scalar_one_or_none()

        # Equity = cash + capital en posiciones abiertas
        positions_result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.size_usd), 0.0))
            .where(Trade.status == "OPEN")
        )
        capital_in_positions = float(positions_result.scalar() or 0.0)
        equity = (state.capital_usd + capital_in_positions) if state else 0

        return {
            "capital_usd": state.capital_usd if state else 0,
            "peak_capital_usd": state.peak_capital_usd if state else 0,
            "total_pnl": await self.get_total_pnl(),
            "total_costs": await self.get_total_costs(),
            "net_profit": await self.get_net_profit(),
            "net_7d": await self.get_net_profit(days=7),
            "net_14d": await self.get_net_profit(days=14),
            "win_rate": await self.get_win_rate(),
            "drawdown_pct": (
                (state.peak_capital_usd - equity) / state.peak_capital_usd
                if state and state.peak_capital_usd > 0
                else 0
            ),
        }
