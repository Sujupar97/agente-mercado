"""Orchestrador multi-estrategia — data compartida, ejecución por estrategia.

Flujo:
1. Fetch tickers (compartido)
2. Pre-filtro técnico (compartido)
3. Extraer símbolos viables
4. Cada estrategia habilitada genera señales basadas en reglas técnicas
5. Tracker verifica posiciones abiertas (TP/SL/trailing/partials)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.analysis.technical import TechnicalPreFilter
from app.core.strategy_runner import StrategyRunner
from app.data.ohlcv import OHLCVProvider
from app.db.database import async_session_factory
from app.llm.budget import LLMBudget
from app.llm.gemini import GeminiClient
from app.markets.crypto_exchange import CryptoExchangeProvider
from app.notifications.telegram import TelegramNotifier
from app.strategies.registry import STRATEGIES
from app.trading.executor import OrderExecutor
from app.trading.tracker import PositionTracker

log = logging.getLogger(__name__)


class StrategyOrchestrator:
    """Orquesta múltiples estrategias compartiendo fetch de datos."""

    def __init__(self) -> None:
        self._market_provider = CryptoExchangeProvider()
        self._llm = GeminiClient()
        self._budget = LLMBudget()
        self._executor = OrderExecutor()
        self._notifier = TelegramNotifier()
        self._ohlcv = OHLCVProvider()

        # Un runner por estrategia habilitada
        self._runners: dict[str, StrategyRunner] = {}
        for strategy_id, config in STRATEGIES.items():
            if not config.enabled:
                log.info("Estrategia %s deshabilitada — omitida", strategy_id)
                continue
            self._runners[strategy_id] = StrategyRunner(
                config=config,
                llm=self._llm,
                budget=self._budget,
                executor=self._executor,
                notifier=self._notifier,
                ohlcv=self._ohlcv,
            )

    async def run_cycle(self) -> None:
        """Ciclo compartido: fetch datos una vez, luego ejecutar cada estrategia."""
        cycle_start = datetime.now(timezone.utc)
        log.info("=== Inicio de ciclo multi-estrategia ===")

        try:
            # FASE 1: FETCH COMPARTIDO (una vez para todas las estrategias)
            tickers = await self._market_provider.fetch_tickers(limit=500)
            log.info("Paso 1: %d pares obtenidos", len(tickers))

            viable = [
                t for t in tickers
                if t.bid_ask_spread_pct < 0.5 and t.price > 0
            ]
            log.info("Paso 2: %d pares viables", len(viable))

            if not viable:
                log.warning("Sin mercados viables")
                return

            # Pre-filtro técnico compartido (momentum + volumen)
            pre_filtered = TechnicalPreFilter.filter(viable)
            if not pre_filtered:
                pre_filtered = viable[:50]
            log.info("Paso 3: %d pares pre-filtrados", len(pre_filtered))

            # Extraer símbolos para los runners (sin enriquecimiento LLM)
            top_symbols = [t.symbol for t in pre_filtered[:100]]

            # Limpiar cache OHLCV del ciclo anterior
            self._ohlcv.clear_cache()

            # FASE 2: POR ESTRATEGIA (secuencial para controlar API calls)
            total_trades = 0
            async with async_session_factory() as session:
                for strategy_id, runner in self._runners.items():
                    if not runner.should_run_this_cycle():
                        log.debug("[%s] No toca este ciclo", strategy_id)
                        continue

                    try:
                        trades = await runner.run(
                            top_symbols=top_symbols,
                            session=session,
                            tickers_count=len(tickers),
                        )
                        total_trades += trades
                    except Exception:
                        log.exception("Error en estrategia %s", strategy_id)

                await session.commit()

            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            log.info(
                "=== Ciclo multi-estrategia completado en %.1fs | "
                "Escaneados=%d | Trades totales=%d ===",
                elapsed, len(tickers), total_trades,
            )

        except Exception:
            log.exception("Error fatal en ciclo multi-estrategia")

    async def close(self) -> None:
        """Libera todos los recursos."""
        await self._market_provider.close()
        await self._llm.close()
        await self._budget.close()
        await self._executor.close()
        await self._notifier.close()
        await self._ohlcv.close()
