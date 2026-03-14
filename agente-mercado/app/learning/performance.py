"""Motor de analisis de rendimiento — el cerebro del sistema de aprendizaje."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SignalOutcome, Trade

log = logging.getLogger(__name__)

MIN_TRADES_FOR_REPORT = 30
MIN_TRADES_PER_SYMBOL = 5
MIN_TRADES_PER_BUCKET = 10


@dataclass
class SymbolStats:
    symbol: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float
    avg_hold_minutes: float


@dataclass
class DirectionStats:
    direction: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float


@dataclass
class HourStats:
    hour: int
    total_trades: int
    wins: int
    win_rate: float
    total_pnl: float


@dataclass
class CalibrationBucket:
    confidence_range: str
    confidence_lower: float
    confidence_upper: float
    predicted_win_rate: float
    actual_win_rate: float
    trade_count: int
    calibration_error: float


@dataclass
class ModelStats:
    model: str
    total_trades: int
    wins: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float


@dataclass
class PerformanceReport:
    total_trades: int
    win_rate: float
    profit_factor: float
    sortino_ratio: float
    expectancy: float
    best_symbols: list[SymbolStats] = field(default_factory=list)
    worst_symbols: list[SymbolStats] = field(default_factory=list)
    calibration: list[CalibrationBucket] = field(default_factory=list)
    buy_stats: DirectionStats | None = None
    sell_stats: DirectionStats | None = None
    best_hours: list[int] = field(default_factory=list)
    worst_hours: list[int] = field(default_factory=list)
    model_comparison: list[ModelStats] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class PerformanceAnalyzer:
    """Analiza rendimiento historico para alimentar el sistema de aprendizaje."""

    def __init__(
        self, session: AsyncSession, strategy_id: str | None = None,
    ) -> None:
        self._session = session
        self._strategy_id = strategy_id

    def _strategy_filter(self):
        """Retorna filtro SQLAlchemy para strategy_id si está definido."""
        if self._strategy_id:
            return SignalOutcome.strategy_id == self._strategy_id
        return True  # No filter — all strategies

    async def get_outcomes_count(self) -> int:
        """Numero total de signal outcomes registrados."""
        q = select(func.count(SignalOutcome.id))
        if self._strategy_id:
            q = q.where(SignalOutcome.strategy_id == self._strategy_id)
        result = await self._session.execute(q)
        return result.scalar() or 0

    async def get_full_report(self, min_trades: int = MIN_TRADES_FOR_REPORT) -> PerformanceReport | None:
        """Genera reporte completo. Retorna None si hay datos insuficientes."""
        total = await self.get_outcomes_count()
        if total < min_trades:
            log.info(
                "Datos insuficientes para reporte: %d/%d trades (strategy=%s)",
                total, min_trades, self._strategy_id or "all",
            )
            return None

        # Calcular todas las metricas
        win_rate = await self._get_global_win_rate()
        profit_factor = await self._get_profit_factor()
        sortino = await self._get_sortino_ratio()
        expectancy = await self._get_expectancy()
        symbols = await self.get_symbol_performance()
        calibration = await self.get_confidence_calibration()
        buy_stats, sell_stats = await self._get_direction_stats()
        hourly = await self.get_hourly_performance()
        models = await self.get_model_comparison()

        # Ordenar simbolos
        symbol_list = list(symbols.values())
        symbol_list.sort(key=lambda s: s.total_pnl, reverse=True)
        best = symbol_list[:5]
        worst = symbol_list[-5:] if len(symbol_list) > 5 else []

        # Mejores/peores horas
        hour_list = sorted(hourly.values(), key=lambda h: h.total_pnl, reverse=True)
        best_hours = [h.hour for h in hour_list[:3] if h.total_pnl > 0]
        worst_hours = [h.hour for h in hour_list[-3:] if h.total_pnl < 0]

        # Generar recomendaciones automaticas
        recommendations = self._generate_recommendations(
            win_rate, profit_factor, calibration, buy_stats, sell_stats, worst,
        )

        return PerformanceReport(
            total_trades=total,
            win_rate=win_rate,
            profit_factor=profit_factor,
            sortino_ratio=sortino,
            expectancy=expectancy,
            best_symbols=best,
            worst_symbols=worst,
            calibration=calibration,
            buy_stats=buy_stats,
            sell_stats=sell_stats,
            best_hours=best_hours,
            worst_hours=worst_hours,
            model_comparison=list(models.values()),
            recommendations=recommendations,
        )

    async def _get_global_win_rate(self) -> float:
        wins_q = select(func.count(SignalOutcome.id)).where(SignalOutcome.hit_tp.is_(True))
        total_q = select(func.count(SignalOutcome.id))
        if self._strategy_id:
            wins_q = wins_q.where(SignalOutcome.strategy_id == self._strategy_id)
            total_q = total_q.where(SignalOutcome.strategy_id == self._strategy_id)
        wins_result = await self._session.execute(wins_q)
        total_result = await self._session.execute(total_q)
        wins = wins_result.scalar() or 0
        total = total_result.scalar() or 1
        return wins / total

    async def _get_profit_factor(self) -> float:
        gp_q = (
            select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
            .where(SignalOutcome.actual_pnl > 0)
        )
        gl_q = (
            select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
            .where(SignalOutcome.actual_pnl < 0)
        )
        if self._strategy_id:
            gp_q = gp_q.where(SignalOutcome.strategy_id == self._strategy_id)
            gl_q = gl_q.where(SignalOutcome.strategy_id == self._strategy_id)
        gross_profit_result = await self._session.execute(gp_q)
        gross_loss_result = await self._session.execute(gl_q)
        gross_profit = float(gross_profit_result.scalar() or 0)
        gross_loss = abs(float(gross_loss_result.scalar() or 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    async def _get_sortino_ratio(self) -> float:
        """Sortino ratio: mean_return / downside_std."""
        q = select(SignalOutcome.actual_return_pct)
        if self._strategy_id:
            q = q.where(SignalOutcome.strategy_id == self._strategy_id)
        result = await self._session.execute(q)
        returns = [row[0] for row in result.all()]
        if len(returns) < 2:
            return 0.0

        mean_return = sum(returns) / len(returns)
        downside_returns = [r for r in returns if r < 0]
        if not downside_returns:
            return float("inf") if mean_return > 0 else 0.0

        downside_var = sum(r ** 2 for r in downside_returns) / len(downside_returns)
        downside_std = math.sqrt(downside_var)
        if downside_std == 0:
            return 0.0
        return mean_return / downside_std

    async def _get_expectancy(self) -> float:
        """Valor esperado por trade en USD: (WR * avg_win) - (LR * avg_loss)."""
        wins_q = select(
            func.count(SignalOutcome.id),
            func.coalesce(func.avg(SignalOutcome.actual_pnl), 0.0),
        ).where(SignalOutcome.actual_pnl > 0)
        losses_q = select(
            func.count(SignalOutcome.id),
            func.coalesce(func.avg(SignalOutcome.actual_pnl), 0.0),
        ).where(SignalOutcome.actual_pnl <= 0)
        total_q = select(func.count(SignalOutcome.id))

        if self._strategy_id:
            wins_q = wins_q.where(SignalOutcome.strategy_id == self._strategy_id)
            losses_q = losses_q.where(SignalOutcome.strategy_id == self._strategy_id)
            total_q = total_q.where(SignalOutcome.strategy_id == self._strategy_id)

        wins_result = await self._session.execute(wins_q)
        losses_result = await self._session.execute(losses_q)
        total_result = await self._session.execute(total_q)

        wins_row = wins_result.one()
        losses_row = losses_result.one()
        total = total_result.scalar() or 1

        win_count = wins_row[0]
        avg_win = float(wins_row[1])
        loss_count = losses_row[0]
        avg_loss = abs(float(losses_row[1]))

        wr = win_count / total
        lr = loss_count / total
        return (wr * avg_win) - (lr * avg_loss)

    async def _get_direction_stats(self) -> tuple[DirectionStats | None, DirectionStats | None]:
        buy = await self._calc_direction_stats("BUY")
        sell = await self._calc_direction_stats("SELL")
        return buy, sell

    async def _calc_direction_stats(self, direction: str) -> DirectionStats | None:
        q = select(
            func.count(SignalOutcome.id),
            func.count(case((SignalOutcome.hit_tp.is_(True), 1))),
            func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0),
            func.coalesce(func.avg(SignalOutcome.actual_pnl), 0.0),
        ).where(SignalOutcome.direction == direction)
        if self._strategy_id:
            q = q.where(SignalOutcome.strategy_id == self._strategy_id)
        result = await self._session.execute(q)
        row = result.one()
        total = row[0]
        if total == 0:
            return None
        wins = row[1]
        losses = total - wins
        total_pnl = float(row[2])
        avg_pnl = float(row[3])

        # Profit factor para esta direccion
        gp_q = (
            select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
            .where(SignalOutcome.direction == direction, SignalOutcome.actual_pnl > 0)
        )
        gl_q = (
            select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
            .where(SignalOutcome.direction == direction, SignalOutcome.actual_pnl < 0)
        )
        if self._strategy_id:
            gp_q = gp_q.where(SignalOutcome.strategy_id == self._strategy_id)
            gl_q = gl_q.where(SignalOutcome.strategy_id == self._strategy_id)
        gp_result = await self._session.execute(gp_q)
        gl_result = await self._session.execute(gl_q)
        gp = float(gp_result.scalar() or 0)
        gl = abs(float(gl_result.scalar() or 0))
        pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)

        return DirectionStats(
            direction=direction,
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate=wins / total,
            total_pnl=total_pnl,
            avg_pnl=avg_pnl,
            profit_factor=pf,
        )

    async def get_symbol_performance(self) -> dict[str, SymbolStats]:
        """Rendimiento por simbolo."""
        q = (
            select(
                SignalOutcome.symbol,
                func.count(SignalOutcome.id),
                func.count(case((SignalOutcome.hit_tp.is_(True), 1))),
                func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0),
                func.coalesce(func.avg(SignalOutcome.actual_pnl), 0.0),
                func.coalesce(func.avg(SignalOutcome.hold_duration_minutes), 0.0),
            )
            .group_by(SignalOutcome.symbol)
            .having(func.count(SignalOutcome.id) >= MIN_TRADES_PER_SYMBOL)
        )
        if self._strategy_id:
            q = q.where(SignalOutcome.strategy_id == self._strategy_id)
        result = await self._session.execute(q)
        stats: dict[str, SymbolStats] = {}
        for row in result.all():
            symbol = row[0]
            total = row[1]
            wins = row[2]
            losses = total - wins
            total_pnl = float(row[3])
            avg_pnl = float(row[4])
            avg_hold = float(row[5])

            # Profit factor per symbol
            gp_q = (
                select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
                .where(SignalOutcome.symbol == symbol, SignalOutcome.actual_pnl > 0)
            )
            gl_q = (
                select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
                .where(SignalOutcome.symbol == symbol, SignalOutcome.actual_pnl < 0)
            )
            if self._strategy_id:
                gp_q = gp_q.where(SignalOutcome.strategy_id == self._strategy_id)
                gl_q = gl_q.where(SignalOutcome.strategy_id == self._strategy_id)
            gp_result = await self._session.execute(gp_q)
            gl_result = await self._session.execute(gl_q)
            gp = float(gp_result.scalar() or 0)
            gl = abs(float(gl_result.scalar() or 0))
            pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)

            stats[symbol] = SymbolStats(
                symbol=symbol,
                total_trades=total,
                wins=wins,
                losses=losses,
                win_rate=wins / total,
                total_pnl=total_pnl,
                avg_pnl=avg_pnl,
                profit_factor=pf,
                avg_hold_minutes=avg_hold,
            )
        return stats

    async def get_hourly_performance(self) -> dict[int, HourStats]:
        """Rendimiento por hora del dia (UTC)."""
        q = select(
            SignalOutcome.hour_of_day,
            func.count(SignalOutcome.id),
            func.count(case((SignalOutcome.hit_tp.is_(True), 1))),
            func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0),
        ).group_by(SignalOutcome.hour_of_day)
        if self._strategy_id:
            q = q.where(SignalOutcome.strategy_id == self._strategy_id)
        result = await self._session.execute(q)
        stats: dict[int, HourStats] = {}
        for row in result.all():
            hour = row[0]
            total = row[1]
            wins = row[2]
            stats[hour] = HourStats(
                hour=hour,
                total_trades=total,
                wins=wins,
                win_rate=wins / total if total > 0 else 0,
                total_pnl=float(row[3]),
            )
        return stats

    async def get_confidence_calibration(self) -> list[CalibrationBucket]:
        """Agrupa por rango de confianza y compara predicho vs real."""
        buckets = [
            (0.35, 0.45), (0.45, 0.55), (0.55, 0.65),
            (0.65, 0.75), (0.75, 0.85),
        ]
        calibration: list[CalibrationBucket] = []

        for lower, upper in buckets:
            q = select(
                func.count(SignalOutcome.id),
                func.count(case((SignalOutcome.hit_tp.is_(True), 1))),
                func.coalesce(func.avg(SignalOutcome.predicted_confidence), 0.0),
            ).where(
                SignalOutcome.predicted_confidence >= lower,
                SignalOutcome.predicted_confidence < upper,
            )
            if self._strategy_id:
                q = q.where(SignalOutcome.strategy_id == self._strategy_id)
            result = await self._session.execute(q)
            row = result.one()
            total = row[0]
            if total < MIN_TRADES_PER_BUCKET:
                continue

            wins = row[1]
            predicted_wr = float(row[2])
            actual_wr = wins / total

            calibration.append(CalibrationBucket(
                confidence_range=f"{lower:.2f}-{upper:.2f}",
                confidence_lower=lower,
                confidence_upper=upper,
                predicted_win_rate=predicted_wr,
                actual_win_rate=actual_wr,
                trade_count=total,
                calibration_error=abs(predicted_wr - actual_wr),
            ))

        return calibration

    async def get_model_comparison(self) -> dict[str, ModelStats]:
        """Comparacion Flash vs Pro."""
        q = select(
            SignalOutcome.llm_model,
            func.count(SignalOutcome.id),
            func.count(case((SignalOutcome.hit_tp.is_(True), 1))),
            func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0),
            func.coalesce(func.avg(SignalOutcome.actual_pnl), 0.0),
        ).group_by(SignalOutcome.llm_model)
        if self._strategy_id:
            q = q.where(SignalOutcome.strategy_id == self._strategy_id)
        result = await self._session.execute(q)
        stats: dict[str, ModelStats] = {}
        for row in result.all():
            model = row[0]
            total = row[1]
            wins = row[2]
            total_pnl = float(row[3])
            avg_pnl = float(row[4])

            gp_q = (
                select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
                .where(SignalOutcome.llm_model == model, SignalOutcome.actual_pnl > 0)
            )
            gl_q = (
                select(func.coalesce(func.sum(SignalOutcome.actual_pnl), 0.0))
                .where(SignalOutcome.llm_model == model, SignalOutcome.actual_pnl < 0)
            )
            if self._strategy_id:
                gp_q = gp_q.where(SignalOutcome.strategy_id == self._strategy_id)
                gl_q = gl_q.where(SignalOutcome.strategy_id == self._strategy_id)
            gp_result = await self._session.execute(gp_q)
            gl_result = await self._session.execute(gl_q)
            gp = float(gp_result.scalar() or 0)
            gl = abs(float(gl_result.scalar() or 0))
            pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)

            stats[model] = ModelStats(
                model=model,
                total_trades=total,
                wins=wins,
                win_rate=wins / total if total > 0 else 0,
                total_pnl=total_pnl,
                avg_pnl=avg_pnl,
                profit_factor=pf,
            )
        return stats

    def _generate_recommendations(
        self,
        win_rate: float,
        profit_factor: float,
        calibration: list[CalibrationBucket],
        buy_stats: DirectionStats | None,
        sell_stats: DirectionStats | None,
        worst_symbols: list[SymbolStats],
    ) -> list[str]:
        """Genera recomendaciones automaticas basadas en metricas."""
        recs: list[str] = []

        if win_rate < 0.40:
            recs.append(
                f"Win rate bajo ({win_rate:.0%}). Considerar subir min_confidence."
            )
        if profit_factor < 1.0:
            recs.append(
                f"Profit factor < 1 ({profit_factor:.2f}). Sistema perdiendo dinero."
            )

        # Calibracion
        for bucket in calibration:
            if bucket.calibration_error > 0.15:
                if bucket.predicted_win_rate > bucket.actual_win_rate:
                    recs.append(
                        f"Rango {bucket.confidence_range}: LLM sobreestima "
                        f"(predicho {bucket.predicted_win_rate:.0%}, real {bucket.actual_win_rate:.0%})."
                    )

        # Direccion
        if buy_stats and sell_stats:
            if buy_stats.win_rate > sell_stats.win_rate + 0.15:
                recs.append(
                    f"BUY ({buy_stats.win_rate:.0%}) supera SELL ({sell_stats.win_rate:.0%}). "
                    "Considerar ser mas conservador con SELLs."
                )
            elif sell_stats.win_rate > buy_stats.win_rate + 0.15:
                recs.append(
                    f"SELL ({sell_stats.win_rate:.0%}) supera BUY ({buy_stats.win_rate:.0%}). "
                    "Considerar ser mas conservador con BUYs."
                )

        # Simbolos perdedores
        for sym in worst_symbols:
            if sym.win_rate < 0.30 and sym.total_trades >= MIN_TRADES_PER_SYMBOL:
                recs.append(
                    f"{sym.symbol}: WR {sym.win_rate:.0%} en {sym.total_trades} trades. "
                    "Candidato a blacklist."
                )

        return recs
