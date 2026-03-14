"""Filtros adaptativos — auto-ajuste basado en rendimiento historico."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LearningLog
from app.learning.performance import (
    MIN_TRADES_FOR_REPORT,
    MIN_TRADES_PER_SYMBOL,
    PerformanceAnalyzer,
)

log = logging.getLogger(__name__)


@dataclass
class Adjustment:
    """Un ajuste calculado por el sistema de aprendizaje."""

    type: str  # BLACKLIST_SYMBOL, RAISE_MIN_CONFIDENCE, DIRECTION_BIAS, AVOID_HOUR, BOOST_SYMBOL
    reason: str
    symbol: str = ""
    direction: str = ""
    hour: int = -1
    new_value: float = 0.0


class AdaptiveFilter:
    """Calcula y aplica ajustes automaticos basados en datos historicos."""

    def __init__(
        self, session: AsyncSession, strategy_id: str | None = None,
    ) -> None:
        self._session = session
        self._strategy_id = strategy_id
        self._analyzer = PerformanceAnalyzer(session, strategy_id=strategy_id)

    async def compute_adjustments(self) -> list[Adjustment]:
        """Calcula ajustes sugeridos. Solo si hay 30+ trades cerrados."""
        total = await self._analyzer.get_outcomes_count()
        if total < MIN_TRADES_FOR_REPORT:
            log.info(
                "Aprendizaje [%s]: %d/%d trades — datos insuficientes para ajustes",
                self._strategy_id or "all", total, MIN_TRADES_FOR_REPORT,
            )
            return []

        report = await self._analyzer.get_full_report()
        if not report:
            return []

        adjustments: list[Adjustment] = []

        # 1. Blacklist de simbolos perdedores
        for sym in report.worst_symbols:
            if sym.total_trades >= MIN_TRADES_PER_SYMBOL and sym.win_rate < 0.30:
                adj = Adjustment(
                    type="BLACKLIST_SYMBOL",
                    symbol=sym.symbol,
                    reason=(
                        f"Win rate {sym.win_rate:.0%} en {sym.total_trades} trades, "
                        f"PnL ${sym.total_pnl:.2f}"
                    ),
                )
                adjustments.append(adj)

        # 2. Boost de simbolos ganadores
        for sym in report.best_symbols:
            if sym.total_trades >= MIN_TRADES_PER_SYMBOL and sym.win_rate > 0.70:
                adj = Adjustment(
                    type="BOOST_SYMBOL",
                    symbol=sym.symbol,
                    reason=(
                        f"Win rate {sym.win_rate:.0%} en {sym.total_trades} trades, "
                        f"PnL ${sym.total_pnl:.2f}"
                    ),
                )
                adjustments.append(adj)

        # 3. Ajuste de confianza minima basado en calibracion
        for bucket in report.calibration:
            if bucket.trade_count >= 10 and bucket.actual_win_rate < 0.35:
                adj = Adjustment(
                    type="RAISE_MIN_CONFIDENCE",
                    new_value=bucket.confidence_upper,
                    reason=(
                        f"Rango {bucket.confidence_range} solo acierta "
                        f"{bucket.actual_win_rate:.0%} en {bucket.trade_count} trades"
                    ),
                )
                adjustments.append(adj)

        # 4. Sesgo de direccion
        if report.buy_stats and report.sell_stats:
            if (
                report.buy_stats.total_trades >= 15
                and report.sell_stats.total_trades >= 15
            ):
                if report.buy_stats.win_rate > report.sell_stats.win_rate + 0.15:
                    adjustments.append(Adjustment(
                        type="DIRECTION_BIAS",
                        direction="BUY",
                        reason=(
                            f"BUY WR={report.buy_stats.win_rate:.0%} vs "
                            f"SELL WR={report.sell_stats.win_rate:.0%}"
                        ),
                    ))
                elif report.sell_stats.win_rate > report.buy_stats.win_rate + 0.15:
                    adjustments.append(Adjustment(
                        type="DIRECTION_BIAS",
                        direction="SELL",
                        reason=(
                            f"SELL WR={report.sell_stats.win_rate:.0%} vs "
                            f"BUY WR={report.buy_stats.win_rate:.0%}"
                        ),
                    ))

        # 5. Evitar horas malas
        hourly = await self._analyzer.get_hourly_performance()
        for hour, stats in hourly.items():
            if stats.total_trades >= 10 and stats.win_rate < 0.25:
                adjustments.append(Adjustment(
                    type="AVOID_HOUR",
                    hour=hour,
                    reason=(
                        f"Hora {hour}:00 UTC: WR {stats.win_rate:.0%} "
                        f"en {stats.total_trades} trades, PnL ${stats.total_pnl:.2f}"
                    ),
                ))

        # Loguear ajustes
        for adj in adjustments:
            log.info(
                "[%s] Ajuste adaptativo: %s | %s",
                self._strategy_id or "all", adj.type, adj.reason,
            )

        return adjustments

    async def log_adjustments(self, adjustments: list[Adjustment]) -> None:
        """Guarda ajustes en la tabla LearningLog para auditoria."""
        for adj in adjustments:
            total = await self._analyzer.get_outcomes_count()
            entry = LearningLog(
                adjustment_type=adj.type,
                parameter=adj.symbol or adj.direction or str(adj.hour),
                old_value=None,
                new_value=str(adj.new_value) if adj.new_value else adj.symbol or adj.direction,
                reason=adj.reason,
                trades_analyzed=total,
                strategy_id=self._strategy_id or "momentum",
            )
            self._session.add(entry)
        if adjustments:
            await self._session.flush()

    def get_blacklisted_symbols(self, adjustments: list[Adjustment]) -> set[str]:
        """Extrae simbolos blacklisteados de los ajustes."""
        return {a.symbol for a in adjustments if a.type == "BLACKLIST_SYMBOL"}

    def get_boosted_symbols(self, adjustments: list[Adjustment]) -> set[str]:
        """Extrae simbolos boosteados de los ajustes."""
        return {a.symbol for a in adjustments if a.type == "BOOST_SYMBOL"}

    def get_direction_bias(self, adjustments: list[Adjustment]) -> str | None:
        """Retorna la direccion favorecida, si hay bias."""
        for a in adjustments:
            if a.type == "DIRECTION_BIAS":
                return a.direction
        return None

    def get_avoided_hours(self, adjustments: list[Adjustment]) -> set[int]:
        """Extrae horas a evitar."""
        return {a.hour for a in adjustments if a.type == "AVOID_HOUR"}
