"""Loop principal del agente — 10 pasos cada ciclo."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func as sa_func, select

from app.analysis.inefficiency import InefficiencyDetector
from app.analysis.probability import ProbabilityEngine
from app.analysis.technical import TechnicalPreFilter
from app.config import settings
from app.core.state import StateManager
from app.data.router import DataRouter
from app.db.database import async_session_factory
from app.db.models import AgentState, Signal, Trade
from app.learning.adaptive import AdaptiveFilter
from app.llm.budget import LLMBudget
from app.llm.gemini import GeminiClient
from app.markets.crypto_exchange import CryptoExchangeProvider
from app.notifications.telegram import TelegramNotifier
from app.pnl.cost_tracker import CostTracker
from app.risk.manager import RiskManager
from app.trading.executor import OrderExecutor, TradeOrder
from app.trading.tracker import PositionTracker

log = logging.getLogger(__name__)


class AgentLoop:
    """Orquestador principal — ejecuta el ciclo de trading cada N minutos."""

    def __init__(self) -> None:
        self._market_provider = CryptoExchangeProvider()
        self._data_router = DataRouter()
        self._llm = GeminiClient()
        self._budget = LLMBudget()
        self._prob_engine = ProbabilityEngine(self._llm, self._budget)
        self._inefficiency = InefficiencyDetector()
        self._executor = OrderExecutor()
        self._notifier = TelegramNotifier()
        self._cycle_count = 0  # Contador para alternar modelo Flash/Pro
        self._adjustments: list = []  # Ajustes adaptativos del sistema de aprendizaje
        self._consecutive_empty_cycles = 0  # Ciclos sin senales para auto-recovery

    async def run_cycle(self) -> None:
        """Ejecuta un ciclo completo del agente (10 pasos)."""
        cycle_start = datetime.now(timezone.utc)
        log.info("=== Inicio de ciclo ===")

        async with async_session_factory() as session:
            state_mgr = StateManager(session)
            risk_mgr = RiskManager(session)
            cost_tracker = CostTracker(session)
            tracker = PositionTracker(session, self._executor)

            try:
                # PASO 1: Verificar modo del agente
                state = await state_mgr.ensure_state()
                if state.mode in ("SHUTDOWN", "PAUSED"):
                    log.info("Agente en modo %s — saltando ciclo", state.mode)
                    return
                is_simulation = state.mode == "SIMULATION"
                log.info(
                    "Modo: %s | Capital: $%.2f | Posiciones: %d",
                    state.mode, state.capital_usd, state.positions_open,
                )

                # PASO 2: Obtener pares activos
                tickers = await self._market_provider.fetch_tickers(limit=500)
                log.info("Paso 2: %d pares obtenidos", len(tickers))

                # PASO 3: Filtrar viables (ya filtrado por volumen en el provider)
                viable = [
                    t for t in tickers
                    if t.bid_ask_spread_pct < 0.5 and t.price > 0
                ]
                log.info("Paso 3: %d pares viables (spread < 0.5%%)", len(viable))

                if not viable:
                    log.warning("Sin mercados viables — finalizando ciclo")
                    await state_mgr.update_cycle_stats(len(tickers), 0)
                    await session.commit()
                    return

                # PASO 3.5: Pre-filtro técnico (GRATIS — no usa LLM)
                pre_filtered = TechnicalPreFilter.filter(viable)
                if not pre_filtered:
                    log.warning("Pre-filtro: ningún par con momentum suficiente")
                    pre_filtered = viable[:50]  # Fallback: usar top 50 por volumen
                log.info("Paso 3.5: %d pares pre-filtrados (de %d viables)", len(pre_filtered), len(viable))

                # PASO 3.6: Filtros adaptativos (basados en aprendizaje)
                if self._cycle_count % 12 == 0:  # Recalcular cada hora
                    adaptive = AdaptiveFilter(session)
                    self._adjustments = await adaptive.compute_adjustments()
                    if self._adjustments:
                        await adaptive.log_adjustments(self._adjustments)
                    log.info("Paso 3.6: %d ajustes adaptativos calculados", len(self._adjustments))

                if self._adjustments:
                    adaptive_filter = AdaptiveFilter(session)
                    blacklisted = adaptive_filter.get_blacklisted_symbols(self._adjustments)
                    if blacklisted:
                        before = len(pre_filtered)
                        pre_filtered = [t for t in pre_filtered if t.symbol not in blacklisted]
                        log.info(
                            "Paso 3.6: %d pares blacklisteados removidos (de %d a %d)",
                            before - len(pre_filtered), before, len(pre_filtered),
                        )

                # PASO 4: Enriquecer con datos externos
                enriched = await self._data_router.enrich(pre_filtered[:150])
                log.info("Paso 4: %d pares enriquecidos con datos externos", len(enriched))

                # PASO 5: Estimar valor justo con LLM
                # Modelo dual: Flash para ciclos normales, Pro cada N ciclos
                use_deep = (self._cycle_count % settings.deep_analysis_interval == 0)
                model_for_cycle = settings.gemini_model if use_deep else settings.gemini_fallback_model
                log.info(
                    "Paso 5: usando modelo %s (%s, ciclo #%d)",
                    model_for_cycle,
                    "PROFUNDO" if use_deep else "rutina",
                    self._cycle_count,
                )
                signals = await self._prob_engine.estimate_all(
                    enriched, model_override=model_for_cycle, session=session,
                )
                log.info("Paso 5: %d señales generadas por LLM", len(signals))

                # Guardar señales en BD y capturar IDs para enlazar con trades
                signal_ids: dict[str, int] = {}
                for sig in signals:
                    db_signal = Signal(
                        market_id=f"binance:{sig.symbol}",
                        symbol=sig.symbol,
                        estimated_value=0,  # Se calcula del deviation
                        market_price=0,
                        deviation_pct=sig.deviation_pct,
                        direction=sig.direction,
                        confidence=sig.confidence,
                        take_profit_pct=sig.take_profit_pct,
                        stop_loss_pct=sig.stop_loss_pct,
                        llm_model=model_for_cycle,
                        llm_prompt_hash="",
                        llm_response_summary=sig.rationale[:500],
                        data_sources_used=sig.data_sources,
                    )
                    session.add(db_signal)
                    await session.flush()
                    signal_ids[sig.symbol] = db_signal.id

                # PASO 6: Detectar ineficiencias
                opportunities = self._inefficiency.detect(signals)
                log.info("Paso 6: %d oportunidades detectadas", len(opportunities))

                # PASO 7: Calcular position sizing con Kelly + Risk
                # Usar equity (cash + posiciones) para sizing, no solo cash
                equity_result = await session.execute(
                    select(sa_func.coalesce(sa_func.sum(Trade.size_usd), 0.0))
                    .where(Trade.status == "OPEN")
                )
                capital_in_positions = float(equity_result.scalar() or 0.0)
                equity = state.capital_usd + capital_in_positions

                approved_trades: list[TradeOrder] = []
                for opp in opportunities:
                    sig = opp.signal
                    pos_result = await risk_mgr.calculate_position(
                        p_win=sig.confidence,
                        take_profit_pct=sig.take_profit_pct,
                        stop_loss_pct=sig.stop_loss_pct,
                        capital=equity,
                    )

                    if not pos_result.approved:
                        log.debug("Trade rechazado para %s: %s", sig.symbol, pos_result.rejection_reason)
                        continue

                    # Verificar límites globales
                    ok, reason = await risk_mgr.check_all_limits(pos_result.size_usd)
                    if not ok:
                        log.info("Límite de riesgo: %s para %s", reason, sig.symbol)
                        continue

                    approved_trades.append(
                        TradeOrder(
                            symbol=sig.symbol,
                            direction=sig.direction,
                            size_usd=pos_result.size_usd,
                            take_profit_pct=sig.take_profit_pct,
                            stop_loss_pct=sig.stop_loss_pct,
                            kelly_fraction=pos_result.kelly_adjusted,
                        )
                    )

                log.info("Paso 7: %d trades aprobados por risk manager", len(approved_trades))

                # PASO 8: Ejecutar órdenes
                trades_executed = 0
                for order in approved_trades:
                    # Verificar capital disponible antes de cada trade
                    if order.size_usd > state.capital_usd:
                        log.info(
                            "Capital insuficiente: $%.2f necesario, $%.2f disponible — saltando %s",
                            order.size_usd, state.capital_usd, order.symbol,
                        )
                        continue

                    if is_simulation:
                        # Paper trade — usar precios reales de Binance
                        try:
                            exchange = self._market_provider._exchanges[0][1]
                            ticker = await exchange.fetch_ticker(order.symbol)
                            current_price = ticker.get("last", 0)
                            if current_price <= 0:
                                log.warning("Precio inválido para %s, saltando", order.symbol)
                                continue

                            quantity = order.size_usd / current_price
                            sim_fees = order.size_usd * 0.001  # 0.1% fee simulado

                            if order.direction == "BUY":
                                tp_price = current_price * (1 + order.take_profit_pct)
                                sl_price = current_price * (1 - order.stop_loss_pct)
                            else:
                                tp_price = current_price * (1 - order.take_profit_pct)
                                sl_price = current_price * (1 + order.stop_loss_pct)

                            trade = Trade(
                                signal_id=signal_ids.get(order.symbol),
                                market_id=f"binance:{order.symbol}",
                                symbol=order.symbol,
                                direction=order.direction,
                                size_usd=order.size_usd,
                                quantity=quantity,
                                entry_price=current_price,
                                take_profit_price=tp_price,
                                stop_loss_price=sl_price,
                                kelly_fraction=order.kelly_fraction,
                                fees=sim_fees,
                                status="OPEN",
                                is_simulation=True,
                            )
                            session.add(trade)

                            state.capital_usd -= order.size_usd
                            state.positions_open += 1
                            trades_executed += 1

                            log.info(
                                "SIM Trade: %s %s %.6f @ $%.4f | TP=$%.4f SL=$%.4f | Size=$%.2f",
                                order.direction, order.symbol, quantity,
                                current_price, tp_price, sl_price, order.size_usd,
                            )
                        except Exception:
                            log.exception("Error en paper trade %s", order.symbol)
                    else:
                        result = await self._executor.execute(order)
                        if result.success:
                            trade = Trade(
                                signal_id=signal_ids.get(order.symbol),
                                market_id=f"binance:{result.symbol}",
                                symbol=result.symbol,
                                direction=result.direction,
                                size_usd=result.size_usd,
                                quantity=result.quantity,
                                entry_price=result.entry_price,
                                take_profit_price=result.take_profit_price,
                                stop_loss_price=result.stop_loss_price,
                                kelly_fraction=result.kelly_fraction,
                                fees=result.fees,
                                status="OPEN",
                                order_id=result.order_id,
                                is_simulation=False,
                            )
                            session.add(trade)

                            # Registrar fee
                            if result.fees > 0:
                                await cost_tracker.log_trading_fee("binance", result.fees)

                            # Actualizar capital y posiciones
                            state.capital_usd -= result.size_usd
                            state.positions_open += 1

                            # Notificar
                            await self._notifier.send_trade_alert(
                                result.direction, result.symbol,
                                result.size_usd, result.entry_price,
                                result.kelly_fraction,
                            )
                            trades_executed += 1

                log.info("Paso 8: %d trades ejecutados", trades_executed)

                # PASO 9: Verificar posiciones abiertas existentes
                closed = await tracker.check_open_positions()
                if closed > 0:
                    log.info("Paso 9: %d posiciones cerradas (TP/SL)", closed)

                # PASO 10: Actualizar P&L, costos, evaluar supervivencia
                await cost_tracker.log_cycle_costs()
                await state_mgr.update_cycle_stats(len(tickers), trades_executed)

                survival = await state_mgr.evaluate_survival()
                if survival.action == "SIMULATION" and state.mode == "LIVE":
                    await state_mgr.set_mode("SIMULATION")
                    await self._notifier.send(
                        f"AGENTE → SIMULACION\n"
                        f"Razón: {survival.reason}\n"
                        f"Capital: ${state.capital_usd:.2f}\n"
                        f"Net 7d: ${survival.net_7d:.2f}\n"
                        f"Net 14d: ${survival.net_14d:.2f}"
                    )
                elif survival.action == "SHUTDOWN" and not is_simulation:
                    await state_mgr.set_mode("SHUTDOWN")
                    await self._notifier.send(
                        f"AGENTE APAGADO\nRazón: {survival.reason}"
                    )
                elif survival.action == "WARNING":
                    log.warning("Supervivencia: %s", survival.reason)

                await session.commit()
                self._cycle_count += 1

                # Monitoreo de ciclos vacios — auto-recovery
                if len(signals) == 0:
                    self._consecutive_empty_cycles += 1
                    log.warning(
                        "ALERTA: %d ciclos consecutivos sin senales",
                        self._consecutive_empty_cycles,
                    )
                    if self._consecutive_empty_cycles >= 6:
                        log.error(
                            "CRITICO: %d ciclos sin actividad — verificando presupuesto LLM",
                            self._consecutive_empty_cycles,
                        )
                        budget_usage = await self._budget.get_usage()
                        if budget_usage["rpd"] >= budget_usage["rpd_limit"]:
                            log.warning("Auto-recovery: presupuesto LLM agotado, esperando reset diario")
                else:
                    self._consecutive_empty_cycles = 0

                elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                log.info(
                    "=== Ciclo #%d completado en %.1fs | Escaneados=%d | Señales=%d | "
                    "Oportunidades=%d | Trades=%d | Cerrados=%d ===",
                    self._cycle_count, elapsed, len(tickers), len(signals),
                    len(opportunities), trades_executed, closed,
                )

            except Exception:
                log.exception("Error fatal en ciclo del agente")
                await session.rollback()
                await self._notifier.send("ERROR CRITICO en ciclo del agente — revisar logs")

    async def close(self) -> None:
        """Libera todos los recursos."""
        await self._market_provider.close()
        await self._data_router.close()
        await self._llm.close()
        await self._budget.close()
        await self._executor.close()
        await self._notifier.close()
