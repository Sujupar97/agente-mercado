"""Motor de estimación de probabilidad — combina indicadores técnicos + LLM."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.data.router import EnrichedMarket
from app.learning.performance import PerformanceAnalyzer, MIN_TRADES_FOR_REPORT
from app.llm.base import LLMClient, ProbabilityEstimate
from app.llm.budget import LLMBudget
from app.llm.prompts import PERFORMANCE_CONTEXT
from app.strategies.registry import StrategyConfig

log = logging.getLogger(__name__)


def _chunk(lst: list, size: int) -> list[list]:
    """Divide una lista en chunks de tamaño `size`."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


class ProbabilityEngine:
    """Estima probabilidades/valor justo usando LLM + datos externos."""

    def __init__(self, llm_client: LLMClient, budget: LLMBudget) -> None:
        self._llm = llm_client
        self._budget = budget

    async def estimate_all(
        self,
        markets: list[EnrichedMarket],
        model_override: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[ProbabilityEstimate]:
        """Estima valor justo para todos los mercados (en batches).

        Args:
            markets: Mercados enriquecidos a analizar.
            model_override: Modelo LLM específico a usar para este ciclo.
            session: Sesión de BD para generar contexto de rendimiento.
        """
        # Generar contexto de rendimiento si hay datos suficientes
        perf_context = ""
        if session:
            perf_context = await self._build_performance_context(session)

        all_estimates: list[ProbabilityEstimate] = []
        batches = _chunk(markets, settings.llm_batch_size)

        for i, batch in enumerate(batches):
            # Verificar presupuesto LLM
            if not await self._budget.can_call():
                log.warning(
                    "Presupuesto LLM agotado en batch %d/%d, saltando %d mercados",
                    i + 1, len(batches), len(batch),
                )
                break

            try:
                estimates = await self._llm.estimate_fair_values(
                    batch,
                    model_override=model_override,
                    performance_context=perf_context,
                )
                await self._budget.record_call()
                all_estimates.extend(estimates)
                log.info(
                    "Batch %d/%d: %d señales de %d mercados",
                    i + 1, len(batches), len(estimates), len(batch),
                )
            except Exception:
                log.exception("Error en batch %d/%d", i + 1, len(batches))

        return all_estimates

    async def _build_performance_context(
        self, session: AsyncSession, strategy_id: str = "momentum",
    ) -> str:
        """Genera contexto de rendimiento para inyectar en el prompt del LLM."""
        try:
            analyzer = PerformanceAnalyzer(session, strategy_id=strategy_id)
            total = await analyzer.get_outcomes_count()
            if total < MIN_TRADES_FOR_REPORT:
                return ""

            report = await analyzer.get_full_report()
            if not report:
                return ""

            # Formatear simbolos
            best_str = "\n".join(
                f"  - {s.symbol}: WR {s.win_rate:.0%}, PnL ${s.total_pnl:.2f} ({s.total_trades} trades)"
                for s in report.best_symbols[:5]
            ) or "  (datos insuficientes)"

            worst_str = "\n".join(
                f"  - {s.symbol}: WR {s.win_rate:.0%}, PnL ${s.total_pnl:.2f} ({s.total_trades} trades)"
                for s in report.worst_symbols[:5]
            ) or "  (datos insuficientes)"

            # Calibracion
            cal_notes = []
            for bucket in report.calibration:
                if bucket.calibration_error > 0.10:
                    if bucket.predicted_win_rate > bucket.actual_win_rate:
                        cal_notes.append(
                            f"  - Rango {bucket.confidence_range}: predicho {bucket.predicted_win_rate:.0%}, "
                            f"real {bucket.actual_win_rate:.0%} — SOBREESTIMAS"
                        )
                    else:
                        cal_notes.append(
                            f"  - Rango {bucket.confidence_range}: predicho {bucket.predicted_win_rate:.0%}, "
                            f"real {bucket.actual_win_rate:.0%} — SUBESTIMAS"
                        )
            cal_str = "\n".join(cal_notes) or "  Calibracion aceptable"

            # Direccion
            buy_wr = f"{report.buy_stats.win_rate:.0%}" if report.buy_stats else "N/A"
            sell_wr = f"{report.sell_stats.win_rate:.0%}" if report.sell_stats else "N/A"
            dir_rec = "Ambas direcciones similares"
            if report.buy_stats and report.sell_stats:
                if report.buy_stats.win_rate > report.sell_stats.win_rate + 0.10:
                    dir_rec = "BUY funciona mejor. Ser mas selectivo con SELL."
                elif report.sell_stats.win_rate > report.buy_stats.win_rate + 0.10:
                    dir_rec = "SELL funciona mejor. Ser mas selectivo con BUY."

            context = PERFORMANCE_CONTEXT.format(
                total_trades=report.total_trades,
                win_rate=f"{report.win_rate:.0%}",
                profit_factor=f"{report.profit_factor:.2f}",
                expectancy=f"${report.expectancy:.4f}",
                best_symbols=best_str,
                worst_symbols=worst_str,
                calibration_notes=cal_str,
                buy_wr=buy_wr,
                sell_wr=sell_wr,
                direction_recommendation=dir_rec,
                best_hours=", ".join(f"{h}:00" for h in report.best_hours) or "N/A",
                worst_hours=", ".join(f"{h}:00" for h in report.worst_hours) or "N/A",
            )
            log.info(
                "Contexto de rendimiento generado: %d trades, WR %.0f%%, PF %.2f",
                report.total_trades, report.win_rate * 100, report.profit_factor,
            )
            return context

        except Exception:
            log.exception("Error generando contexto de rendimiento")
            return ""

    async def estimate_all_for_strategy(
        self,
        markets: list[EnrichedMarket],
        config: StrategyConfig,
        session: AsyncSession | None = None,
        ohlcv_data: dict[str, dict] | None = None,
        strategy_id: str = "momentum",
    ) -> list[ProbabilityEstimate]:
        """Estima valor justo usando prompts y budget de una estrategia especifica."""
        # Contexto de rendimiento por estrategia + aprendizaje interpretativo
        perf_context = ""
        if session:
            perf_context = await self._build_performance_context(
                session, strategy_id=strategy_id,
            )
            # Inyectar contexto interpretativo del último reporte de aprendizaje
            try:
                from app.learning.bitacora_engine import BitacoraEngine
                engine = BitacoraEngine(session, self._llm)
                learning_ctx = await engine.get_latest_analysis(strategy_id)
                if learning_ctx:
                    perf_context = perf_context + "\n" + learning_ctx if perf_context else learning_ctx
            except Exception:
                log.debug("[%s] No se pudo obtener contexto de aprendizaje", strategy_id)

        # Agregar datos OHLCV al market_data si estan disponibles
        enriched_for_llm = markets
        if ohlcv_data:
            for m in enriched_for_llm:
                sym = m.ticker.symbol
                if sym in ohlcv_data:
                    if not hasattr(m, "_ohlcv_injected"):
                        m._ohlcv_injected = True
                        if hasattr(m, "data_summary") and isinstance(m.data_summary, dict):
                            m.data_summary["ohlcv_indicators"] = ohlcv_data[sym]

        all_estimates: list[ProbabilityEstimate] = []
        batches = _chunk(enriched_for_llm, settings.llm_batch_size)

        for i, batch in enumerate(batches):
            if not await self._budget.can_call_for_strategy(
                strategy_id, config.llm_budget_fraction,
            ):
                log.warning(
                    "[%s] Presupuesto agotado en batch %d/%d",
                    strategy_id, i + 1, len(batches),
                )
                break

            try:
                estimates = await self._llm.estimate_fair_values(
                    batch,
                    model_override=None,
                    performance_context=perf_context,
                    system_prompt_override=config.system_prompt,
                    user_prompt_override=config.user_prompt_template,
                )
                await self._budget.record_call_for_strategy(strategy_id)
                all_estimates.extend(estimates)
                log.info(
                    "[%s] Batch %d/%d: %d senales",
                    strategy_id, i + 1, len(batches), len(estimates),
                )
            except Exception:
                log.exception("[%s] Error en batch %d/%d", strategy_id, i + 1, len(batches))

        return all_estimates
