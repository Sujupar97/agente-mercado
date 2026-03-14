"""Risk Manager — control de limites, drawdown, y position sizing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AgentState, Trade
from app.risk.kelly import kelly_crypto, size_position

log = logging.getLogger(__name__)


@dataclass
class PositionSizeResult:
    """Resultado del calculo de tamano de posicion."""

    size_usd: float
    kelly_raw: float
    kelly_adjusted: float
    approved: bool
    rejection_reason: str = ""


class RiskManager:
    """Gestion de riesgo por estrategia."""

    def __init__(
        self, session: AsyncSession, strategy_id: str = "momentum",
    ) -> None:
        self._session = session
        self._strategy_id = strategy_id

    async def calculate_position(
        self,
        p_win: float,
        take_profit_pct: float,
        stop_loss_pct: float,
        capital: float,
    ) -> PositionSizeResult:
        """Calcula tamano de posicion con Kelly + todos los limites."""
        kelly_raw = kelly_crypto(p_win, take_profit_pct, stop_loss_pct)

        if kelly_raw <= 0:
            return PositionSizeResult(
                size_usd=0, kelly_raw=0, kelly_adjusted=0,
                approved=False, rejection_reason="Kelly <= 0 (sin edge)"
            )

        size = size_position(
            kelly_fraction=kelly_raw,
            capital=capital,
            fractional_kelly=settings.fractional_kelly,
            max_pct=settings.max_per_trade_pct,
        )

        kelly_adjusted = kelly_raw * settings.fractional_kelly

        if size < settings.min_trade_size_usd:
            return PositionSizeResult(
                size_usd=size, kelly_raw=kelly_raw, kelly_adjusted=kelly_adjusted,
                approved=False,
                rejection_reason=f"Tamano ${size:.2f} < minimo ${settings.min_trade_size_usd}",
            )

        return PositionSizeResult(
            size_usd=size, kelly_raw=kelly_raw, kelly_adjusted=kelly_adjusted,
            approved=True,
        )

    async def check_all_limits(self, position_size: float) -> tuple[bool, str]:
        """Verifica todos los limites de riesgo antes de ejecutar un trade."""
        state = await self._get_state()
        if not state:
            return False, "No se encontro estado del agente"

        equity = state.capital_usd + await self._get_capital_in_positions()

        # 1. Drawdown
        drawdown = self._calc_drawdown(equity, state.peak_capital_usd)
        if drawdown >= settings.max_drawdown_pct:
            reason = f"Drawdown {drawdown:.1%} >= limite {settings.max_drawdown_pct:.1%}"
            log.warning("[%s] RiskManager RECHAZO: %s", self._strategy_id, reason)
            return False, reason

        # 2. Posiciones abiertas
        open_count = await self._count_open_positions()
        if open_count >= settings.max_concurrent_positions:
            reason = f"Posiciones abiertas {open_count} >= limite {settings.max_concurrent_positions}"
            log.warning("[%s] RiskManager RECHAZO: %s", self._strategy_id, reason)
            return False, reason

        # 3. Perdida diaria
        daily_loss = await self._get_period_pnl(days=1)
        max_daily = equity * settings.max_daily_loss_pct
        if daily_loss < 0 and abs(daily_loss) >= max_daily:
            reason = f"Perdida diaria ${abs(daily_loss):.2f} >= limite ${max_daily:.2f}"
            log.warning("[%s] RiskManager RECHAZO: %s", self._strategy_id, reason)
            return False, reason

        # 4. Perdida semanal
        weekly_loss = await self._get_period_pnl(days=7)
        max_weekly = equity * settings.max_weekly_loss_pct
        if weekly_loss < 0 and abs(weekly_loss) >= max_weekly:
            reason = f"Perdida semanal ${abs(weekly_loss):.2f} >= limite ${max_weekly:.2f}"
            log.warning("[%s] RiskManager RECHAZO: %s", self._strategy_id, reason)
            return False, reason

        # 5. Capital cubre la posicion
        if position_size > state.capital_usd:
            reason = f"Posicion ${position_size:.2f} > capital ${state.capital_usd:.2f}"
            log.warning("[%s] RiskManager RECHAZO: %s", self._strategy_id, reason)
            return False, reason

        return True, "OK"

    def _calc_drawdown(self, current: float, peak: float) -> float:
        if peak <= 0:
            return 0.0
        return (peak - current) / peak

    async def _get_state(self) -> AgentState | None:
        result = await self._session.execute(
            select(AgentState).where(AgentState.strategy_id == self._strategy_id)
        )
        return result.scalar_one_or_none()

    async def _count_open_positions(self) -> int:
        result = await self._session.execute(
            select(func.count(Trade.id)).where(
                Trade.status == "OPEN",
                Trade.strategy_id == self._strategy_id,
            )
        )
        return result.scalar_one() or 0

    async def _get_capital_in_positions(self) -> float:
        """Capital invertido en posiciones abiertas de esta estrategia."""
        result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.size_usd), 0.0))
            .where(Trade.status == "OPEN", Trade.strategy_id == self._strategy_id)
        )
        return float(result.scalar() or 0.0)

    async def _get_period_pnl(self, days: int) -> float:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
                Trade.status == "CLOSED",
                Trade.closed_at >= since,
                Trade.strategy_id == self._strategy_id,
            )
        )
        return result.scalar_one() or 0.0
