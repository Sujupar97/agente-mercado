"""Motor de bitácora y aprendizaje interpretativo por estrategia."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AgentState,
    Bitacora,
    LearningReport,
    SignalOutcome,
    Strategy,
    Trade,
)
from app.learning.performance import PerformanceAnalyzer
from app.llm.base import LLMClient
from app.strategies.prompts import LEARNING_REPORT_PROMPT, LESSON_BATCH_PROMPT
from app.strategies.registry import STRATEGIES

log = logging.getLogger(__name__)


class BitacoraEngine:
    """Genera lecciones por trade y reportes de aprendizaje por estrategia."""

    def __init__(self, session: AsyncSession, llm: LLMClient) -> None:
        self._session = session
        self._llm = llm

    async def should_generate_report(self, strategy_id: str) -> bool:
        """Verifica si toca generar reporte para esta estrategia."""
        config = STRATEGIES.get(strategy_id)
        if not config:
            return False

        threshold = config.trades_per_learning_report

        # Contar trades cerrados desde el ultimo reporte
        last_report = await self._get_last_report(strategy_id)
        since = last_report.created_at if last_report else datetime(2000, 1, 1, tzinfo=timezone.utc)

        result = await self._session.execute(
            select(func.count(Trade.id)).where(
                Trade.strategy_id == strategy_id,
                Trade.status == "CLOSED",
                Trade.closed_at > since,
            )
        )
        closed_since = result.scalar() or 0
        return closed_since >= threshold

    async def generate_lessons_batch(self, strategy_id: str) -> int:
        """Genera lecciones para trades sin leccion. Retorna cantidad generada."""
        config = STRATEGIES.get(strategy_id)
        if not config:
            return 0

        # Buscar entradas de bitacora sin leccion con trade cerrado
        result = await self._session.execute(
            select(Bitacora)
            .where(
                Bitacora.strategy_id == strategy_id,
                Bitacora.lesson.is_(None),
                Bitacora.pnl.isnot(None),
            )
            .order_by(Bitacora.created_at)
            .limit(10)
        )
        entries = result.scalars().all()
        if not entries:
            return 0

        # Compilar datos de trades para el prompt
        trades_data = []
        for entry in entries:
            trades_data.append({
                "trade_id": entry.trade_id,
                "symbol": entry.symbol,
                "direction": entry.direction,
                "entry_price": entry.entry_price,
                "exit_price": entry.exit_price,
                "pnl": round(entry.pnl, 4) if entry.pnl else 0,
                "exit_reason": entry.exit_reason or "UNKNOWN",
                "hold_minutes": round(entry.hold_duration_minutes or 0, 1),
                "entry_reasoning": (entry.entry_reasoning or "")[:200],
            })

        prompt = LESSON_BATCH_PROMPT.format(
            strategy_name=config.name,
            trades_data=json.dumps(trades_data, ensure_ascii=False),
            count=len(trades_data),
        )

        try:
            # Usar el LLM para generar lecciones
            resp = await self._call_llm_for_json(prompt)
            if not resp or not isinstance(resp, list):
                log.warning("[%s] LLM no retorno lecciones validas", strategy_id)
                return 0

            lessons_map = {item["trade_id"]: item.get("lesson", "") for item in resp}
            applied = 0
            for entry in entries:
                lesson = lessons_map.get(entry.trade_id)
                if lesson:
                    entry.lesson = lesson
                    applied += 1

            log.info("[%s] %d lecciones generadas de %d trades", strategy_id, applied, len(entries))
            return applied

        except Exception:
            log.exception("[%s] Error generando lecciones batch", strategy_id)
            return 0

    async def generate_learning_report(self, strategy_id: str) -> LearningReport | None:
        """Genera un reporte de aprendizaje interpretativo."""
        config = STRATEGIES.get(strategy_id)
        if not config:
            return None

        analyzer = PerformanceAnalyzer(self._session, strategy_id=strategy_id)
        report = await analyzer.get_full_report(min_trades=config.trades_per_learning_report)
        if not report:
            return None

        # Datos de trades cerrados recientes
        last_report = await self._get_last_report(strategy_id)
        since = last_report.created_at if last_report else datetime(2000, 1, 1, tzinfo=timezone.utc)

        trades_result = await self._session.execute(
            select(Trade)
            .where(
                Trade.strategy_id == strategy_id,
                Trade.status == "CLOSED",
                Trade.closed_at > since,
            )
            .order_by(Trade.closed_at.desc())
            .limit(50)
        )
        recent_trades = trades_result.scalars().all()

        # Construir datos del trade para el prompt
        trades_data_lines = []
        for t in recent_trades:
            trades_data_lines.append(
                f"- {t.symbol} {t.direction}: entrada=${t.entry_price:.4f} "
                f"salida=${t.exit_price:.4f} P&L=${t.pnl:.4f} "
                f"({(t.closed_at - t.created_at).total_seconds() / 60:.0f}min)"
            )
        trades_data = "\n".join(trades_data_lines) if trades_data_lines else "Sin datos"

        # Datos de rendimiento por hora
        hourly = await analyzer.get_hourly_performance()
        hourly_lines = []
        for h in sorted(hourly.keys()):
            s = hourly[h]
            hourly_lines.append(
                f"  {h:02d}:00 UTC — {s.total_trades} trades, "
                f"WR {s.win_rate:.0%}, PnL ${s.total_pnl:.2f}"
            )
        hourly_data = "\n".join(hourly_lines) if hourly_lines else "Sin datos"

        # Datos por simbolo
        symbols = await analyzer.get_symbol_performance()
        symbol_lines = []
        for sym in sorted(symbols.values(), key=lambda x: x.total_pnl, reverse=True)[:10]:
            symbol_lines.append(
                f"  {sym.symbol}: {sym.total_trades} trades, "
                f"WR {sym.win_rate:.0%}, PnL ${sym.total_pnl:.2f}, "
                f"PF {sym.profit_factor:.2f}"
            )
        symbol_data = "\n".join(symbol_lines) if symbol_lines else "Sin datos"

        wins = report.buy_stats.wins + report.sell_stats.wins if report.buy_stats and report.sell_stats else 0
        losses = report.total_trades - wins

        prompt = LEARNING_REPORT_PROMPT.format(
            strategy_name=config.name,
            strategy_description=config.description,
            trades_count=len(recent_trades),
            trades_data=trades_data,
            win_rate=report.win_rate,
            profit_factor=report.profit_factor,
            total_pnl=report.expectancy * report.total_trades,
            wins=wins,
            losses=losses,
            hourly_data=hourly_data,
            symbol_data=symbol_data,
        )

        try:
            resp = await self._call_llm_for_json(prompt)
            if not resp or not isinstance(resp, dict):
                log.warning("[%s] LLM no retorno reporte valido", strategy_id)
                return None

            # Numero de reporte
            report_number = 1
            if last_report:
                report_number = last_report.report_number + 1

            lr = LearningReport(
                strategy_id=strategy_id,
                report_number=report_number,
                trades_analyzed=len(recent_trades),
                analysis=resp.get("narrative", ""),
                patterns_found=resp.get("patterns", []),
                recommendations=resp.get("recommendations", []),
                stats_snapshot={
                    "win_rate": report.win_rate,
                    "profit_factor": report.profit_factor,
                    "sortino": report.sortino_ratio,
                    "expectancy": report.expectancy,
                    "total_trades": report.total_trades,
                },
            )
            self._session.add(lr)
            await self._session.flush()

            # Actualizar status_text de la estrategia en BD
            status_text = resp.get("status_text", "")
            if status_text:
                strat_result = await self._session.execute(
                    select(Strategy).where(Strategy.id == strategy_id)
                )
                strat = strat_result.scalar_one_or_none()
                if strat:
                    strat.status_text = status_text

            log.info(
                "[%s] Reporte de aprendizaje #%d generado (%d trades analizados)",
                strategy_id, report_number, len(recent_trades),
            )
            return lr

        except Exception:
            log.exception("[%s] Error generando reporte de aprendizaje", strategy_id)
            return None

    async def get_latest_analysis(self, strategy_id: str) -> str:
        """Obtiene el analisis del ultimo reporte para inyectar en el prompt del LLM."""
        report = await self._get_last_report(strategy_id)
        if not report or not report.analysis:
            return ""

        recommendations = report.recommendations or []
        recs_text = "\n".join(f"- {r}" for r in recommendations) if recommendations else ""

        return (
            f"\n--- CONTEXTO DE APRENDIZAJE (Reporte #{report.report_number}) ---\n"
            f"{report.analysis}\n"
            f"\nRECOMENDACIONES ACTIVAS:\n{recs_text}\n"
            f"--- FIN CONTEXTO ---\n"
        )

    async def _get_last_report(self, strategy_id: str) -> LearningReport | None:
        result = await self._session.execute(
            select(LearningReport)
            .where(LearningReport.strategy_id == strategy_id)
            .order_by(LearningReport.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _call_llm_for_json(self, prompt: str) -> dict | list | None:
        """Llama al LLM con un prompt y parsea la respuesta JSON."""
        import hashlib
        import httpx
        from app.config import settings

        if not settings.gemini_api_key:
            log.error("GEMINI_API_KEY no configurada para bitacora engine")
            return None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{settings.gemini_fallback_model}:generateContent"
        )

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]},
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    url, params={"key": settings.gemini_api_key}, json=payload,
                )
                resp.raise_for_status()

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [p for p in parts if "text" in p and not p.get("thought", False)]
            if not text_parts:
                text_parts = [p for p in parts if "text" in p]
            if not text_parts:
                return None

            text = text_parts[0].get("text", "").strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.strip().startswith("```"))

            return json.loads(text)

        except Exception:
            log.exception("Error en LLM call para bitacora")
            return None
