"""Orquestador Forex — monitorea pares, ejecuta S1/S2 (Oliver Vélez) + S3 (SMC).

Flujo:
1. Verificar sesión de trading (Londres/NY)
2. Verificar que mercado Forex está abierto
3. Para cada instrumento: fetch candles H1+H4+D1 desde broker
4. Para cada estrategia habilitada: generar señales, calcular position size, ejecutar
5. Gestionar posiciones abiertas (break-even, parciales, trailing)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.base import BrokerInterface
from app.broker.models import Candle
from app.config import settings
from app.db.database import async_session_factory
from app.db.models import AgentState, Bitacora, Signal, Trade
from app.forex.instruments import calculate_position_size, get_stepped_risk_base, is_spread_acceptable
from app.forex.sessions import get_current_session, is_forex_market_open, is_trading_session
from app.learning.bitacora_engine import BitacoraEngine
from app.learning.improvement_engine import ImprovementEngine
from app.llm.gemini import GeminiClient
from app.notifications.telegram import TelegramNotifier
from app.signals.rule_engine import (
    ContextResult,
    ForexSignal,
    ForexSignalGenerator,
    ImprovementRuleCheck,
)
from app.signals.connors.signal_engine import ConnorsSignalGenerator
from app.signals.smc.signal_engine import SMCSignalGenerator
from app.signals.turtle.signal_engine import TurtleSignalGenerator
from app.strategies.registry import STRATEGIES

log = logging.getLogger(__name__)


class ForexOrchestrator:
    """Orquesta las estrategias S1/S2 (Oliver Vélez) + S3 (SMC) vía broker."""

    # Máximo tiempo (seg) antes de forzar refresco de contexto
    _CONTEXT_MAX_AGE_SEC = 60 * 60  # 1 hora

    def __init__(self, broker: BrokerInterface) -> None:
        self._broker = broker
        self._llm = GeminiClient()
        self._notifier = TelegramNotifier()
        self._instruments = settings.instruments_list
        self._cycle_count = 0

        # Cache de contexto H1/H4 por estrategia (S1/S2)
        # {strategy_id: {instrument: ContextResult}}
        self._context_cache: dict[str, dict[str, ContextResult]] = {}
        self._context_updated_at: datetime | None = None

        # Cache de BIAS SMC por instrumento (S3)
        # {instrument: "BULLISH"|"BEARISH"|"NEUTRAL"}
        self._smc_bias_cache: dict[str, str] = {}
        self._smc_bias_updated_at: datetime | None = None

        # Trades hoy por estrategia (para max_trades_per_day)
        self._trades_today: dict[str, int] = {}
        self._trades_today_date: str = ""

    # ── Ciclo legacy (wrapper) ─────────────────────────────────

    async def run_cycle(self) -> None:
        """Ciclo completo legacy: contexto + entradas + posiciones."""
        await self.run_context_cycle()
        await self.run_entry_cycle()

    # ── Fase 1: Contexto H1/H4 (cada 15 min) ──────────────────

    async def run_context_cycle(self) -> None:
        """Analiza H1/H4, corre 8 filtros, cachea instrumentos listos."""
        cycle_start = datetime.now(timezone.utc)
        session_name = get_current_session()

        log.info(
            "=== Contexto H1/H4 | Sesión: %s | %s ===",
            session_name, cycle_start.strftime("%H:%M UTC"),
        )

        if not is_forex_market_open():
            log.info("Mercado Forex cerrado — saltando contexto")
            return

        try:
            instruments_data = await self._fetch_all_candles()
            if not instruments_data:
                log.warning("Sin datos de candles — saltando contexto")
                return

            log.info(
                "Contexto: datos para %d instrumentos: %s",
                len(instruments_data), ", ".join(instruments_data.keys()),
            )

            # Correr filtros para cada estrategia
            async with async_session_factory() as session:
                for strategy_id, config in STRATEGIES.items():
                    if not config.enabled:
                        continue

                    if config.signal_type == "smc_institutional":
                        # S3 SMC: calcular BIAS multi-timeframe
                        await self._run_smc_context(config, instruments_data)
                        continue

                    if config.signal_type in ("turtle_breakout", "connors_rsi2"):
                        # S4/S5: no usan contexto H1/H4 — análisis directo en entry cycle
                        continue

                    # S1/S2: 8 filtros de contexto Oliver Vélez
                    improvement_rules = await self._load_improvement_rules(
                        session, strategy_id,
                    )
                    generator = ForexSignalGenerator(config, improvement_rules)
                    context_results = generator.check_context(instruments_data)

                    self._context_cache[strategy_id] = context_results

                    ready = list(context_results.keys())
                    log.info(
                        "[%s] Contexto: %d/%d instrumentos listos%s",
                        strategy_id, len(ready), len(instruments_data),
                        f" ({', '.join(ready)})" if ready else "",
                    )

                self._context_updated_at = datetime.now(timezone.utc)

            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            log.info("=== Contexto completado en %.1fs ===", elapsed)

        except Exception:
            log.exception("Error en ciclo de contexto")

    # ── Fase 2: Entradas M1 (cada 1 min) ──────────────────────

    async def run_entry_cycle(self) -> None:
        """Busca entradas en M1 para instrumentos que pasaron contexto."""
        cycle_start = datetime.now(timezone.utc)

        if not is_forex_market_open():
            return

        if not is_trading_session():
            log.debug("Fuera de sesión de trading — solo gestión de posiciones")
            # Gestionar posiciones incluso fuera de sesión
            try:
                async with async_session_factory() as session:
                    await self._manage_positions(session)
                    await session.commit()
            except Exception:
                log.exception("Error gestionando posiciones")
            return

        # Si no hay cache o es muy viejo, refrescar contexto primero
        if self._context_needs_refresh():
            log.info("Cache de contexto vacío/expirado — refrescando...")
            await self.run_context_cycle()

        try:
            async with async_session_factory() as session:
                # Gestionar posiciones abiertas
                await self._manage_positions(session)

                # Pre-fetch candles por timeframe (compartidos entre estrategias)
                all_instruments = list(set(
                    inst for config in STRATEGIES.values()
                    if config.enabled for inst in config.instruments
                ))
                candle_cache: dict[str, dict[str, list[Candle]]] = {}
                for tf in ("M1", "M5", "H1", "H4"):
                    needed = [i for i in all_instruments
                              if any(c.entry_timeframe == tf and c.enabled for c in STRATEGIES.values())]
                    if needed:
                        candle_cache[tf] = await self._fetch_entry_candles(needed, tf)

                # Buscar entradas para cada estrategia
                total_trades = 0
                for strategy_id, config in STRATEGIES.items():
                    if not config.enabled:
                        continue

                    # Check daily trade limit
                    if self._check_daily_trade_limit(strategy_id, config):
                        continue

                    try:
                        if config.signal_type == "smc_institutional":
                            entry_data = candle_cache.get(config.entry_timeframe, {})
                            h1_data = candle_cache.get("H1", {})
                            improvement_rules = await self._load_improvement_rules(session, config.id)
                            generator = SMCSignalGenerator(config, improvement_rules)
                            signals = generator.scan_entries(self._smc_bias_cache, entry_data, h1_data)

                        elif config.signal_type == "turtle_breakout":
                            entry_data = candle_cache.get(config.entry_timeframe, {})
                            if entry_data:
                                last_results = getattr(self, "_turtle_last_breakout", {})
                                improvement_rules = await self._load_improvement_rules(session, config.id)
                                gen = TurtleSignalGenerator(config, improvement_rules, last_results)
                                signals = gen.scan_entries(entry_data)
                            else:
                                signals = []

                        elif config.signal_type == "connors_rsi2":
                            entry_data = candle_cache.get(config.entry_timeframe, {})
                            if entry_data:
                                improvement_rules = await self._load_improvement_rules(session, config.id)
                                gen = ConnorsSignalGenerator(config, improvement_rules)
                                signals = gen.scan_entries(entry_data)
                            else:
                                signals = []

                        else:
                            # S1/S2: usar context cache + M1 entries
                            context = self._context_cache.get(strategy_id, {})
                            if not context:
                                continue

                            ready_instruments = list(context.keys())
                            entry_data = {i: candle_cache.get(config.entry_timeframe, {}).get(i, [])
                                          for i in ready_instruments
                                          if candle_cache.get(config.entry_timeframe, {}).get(i)}
                            if not entry_data:
                                continue

                            improvement_rules = await self._load_improvement_rules(
                                session, strategy_id,
                            )
                            generator = ForexSignalGenerator(config, improvement_rules)
                            signals = generator.scan_entries(context, entry_data)
                    except Exception:
                        log.exception("[%s] Error generando señales", strategy_id)
                        signals = []

                    for signal in signals:
                        traded = await self._execute_signal(session, signal, strategy_id)
                        if traded:
                            total_trades += 1
                            self._record_daily_trade(strategy_id)

                    # Check learning
                    improvement_engine = ImprovementEngine(session)
                    await self._check_learning(session, strategy_id, improvement_engine)

                # Actualizar AgentState
                for strategy_id in STRATEGIES:
                    state = await self._ensure_state(session, strategy_id)
                    state.last_cycle_at = datetime.now(timezone.utc)

                await session.commit()

                if total_trades > 0:
                    log.info("Total trades ejecutados este ciclo: %d", total_trades)

            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            if elapsed > 5:
                log.info("Ciclo de entrada completado en %.1fs", elapsed)

        except Exception:
            log.exception("Error en ciclo de entrada")

        self._cycle_count += 1

    def _context_needs_refresh(self) -> bool:
        """True si el cache de contexto está vacío o expirado."""
        if not self._context_cache or self._context_updated_at is None:
            return True
        age = (datetime.now(timezone.utc) - self._context_updated_at).total_seconds()
        return age > self._CONTEXT_MAX_AGE_SEC

    async def _fetch_all_candles(self) -> dict[str, dict[str, list[Candle]]]:
        """Fetch candles H1, H4 y D1 para todos los instrumentos (contexto)."""
        result: dict[str, dict[str, list[Candle]]] = {}

        # Check if any strategy needs D1 candles
        needs_d1 = any(
            c.signal_type == "smc_institutional" and c.enabled
            for c in STRATEGIES.values()
        )

        for instrument in self._instruments:
            try:
                candles_h1 = await self._broker.get_candles(instrument, "H1", 250)
                await asyncio.sleep(0.3)  # Rate limit Capital.com
                candles_h4 = await self._broker.get_candles(instrument, "H4", 250)
                await asyncio.sleep(0.3)

                if candles_h1:
                    result[instrument] = {
                        "H1": candles_h1,
                        "H4": candles_h4,
                    }

                    # Fetch D1 for SMC strategies
                    if needs_d1:
                        try:
                            candles_d1 = await self._broker.get_candles(instrument, "D1", 100)
                            result[instrument]["D1"] = candles_d1
                            await asyncio.sleep(0.3)
                        except Exception:
                            log.debug("D1 candles no disponibles para %s", instrument)
            except Exception:
                log.exception("Error fetching candles para %s", instrument)

        return result

    async def _run_smc_context(
        self,
        config: "StrategyConfig",
        instruments_data: dict[str, dict[str, list[Candle]]],
    ) -> None:
        """Fase 1 SMC: calcular BIAS multi-timeframe para S3."""
        # Filter to only this strategy's instruments
        smc_data = {
            inst: tf_data for inst, tf_data in instruments_data.items()
            if inst in config.instruments
        }
        if not smc_data:
            return

        improvement_rules = []  # SMC doesn't use improvement rules yet in context
        generator = SMCSignalGenerator(config, improvement_rules)
        bias_results = generator.check_bias(smc_data)

        self._smc_bias_cache = bias_results
        self._smc_bias_updated_at = datetime.now(timezone.utc)

        ready = [inst for inst, bias in bias_results.items() if bias != "NEUTRAL"]
        log.info(
            "[%s] BIAS: %d/%d instrumentos con dirección%s",
            config.id, len(ready), len(smc_data),
            f" ({', '.join(f'{i}={bias_results[i]}' for i in ready)})" if ready else "",
        )

    async def _run_smc_entries(
        self, session: AsyncSession, config: "StrategyConfig",
    ) -> list[ForexSignal]:
        """Fase 2 SMC: buscar entradas en M5 para instrumentos con BIAS."""
        # Filter instruments with active BIAS
        ready_instruments = [
            inst for inst in config.instruments
            if self._smc_bias_cache.get(inst, "NEUTRAL") != "NEUTRAL"
        ]
        if not ready_instruments:
            return []

        # Fetch M5 candles
        entry_data = await self._fetch_entry_candles(ready_instruments, config.entry_timeframe)
        if not entry_data:
            return []

        # Also fetch H1 for MarketState in signals
        h1_data: dict[str, list[Candle]] = {}
        for inst in ready_instruments:
            try:
                candles_h1 = await self._broker.get_candles(inst, "H1", 250)
                if candles_h1:
                    h1_data[inst] = candles_h1
            except Exception:
                pass

        improvement_rules = await self._load_improvement_rules(session, config.id)
        generator = SMCSignalGenerator(config, improvement_rules)
        return generator.scan_entries(self._smc_bias_cache, entry_data, h1_data)

    def _check_daily_trade_limit(self, strategy_id: str, config) -> bool:
        """Verifica si la estrategia ya alcanzó su límite diario de trades."""
        if config.max_trades_per_day <= 0:
            return False  # Sin límite

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._trades_today_date != today:
            self._trades_today = {}
            self._trades_today_date = today

        count = self._trades_today.get(strategy_id, 0)
        return count >= config.max_trades_per_day

    def _record_daily_trade(self, strategy_id: str) -> None:
        """Registra un trade ejecutado hoy para el límite diario."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._trades_today_date != today:
            self._trades_today = {}
            self._trades_today_date = today
        self._trades_today[strategy_id] = self._trades_today.get(strategy_id, 0) + 1

    async def _fetch_entry_candles(
        self, instruments: list[str], entry_timeframe: str = "M1",
    ) -> dict[str, list[Candle]]:
        """Fetch candles de entrada solo para instrumentos que pasaron contexto."""
        result: dict[str, list[Candle]] = {}

        for instrument in instruments:
            try:
                candles = await self._broker.get_candles(instrument, entry_timeframe, 100)
                if candles:
                    result[instrument] = candles
                await asyncio.sleep(0.3)  # Rate limit Capital.com
            except Exception:
                log.exception("Error fetching %s para %s", entry_timeframe, instrument)

        return result

    async def _load_improvement_rules(
        self, session: AsyncSession, strategy_id: str,
    ) -> list[ImprovementRuleCheck]:
        """Carga las improvement rules activas para una estrategia."""
        improvement_engine = ImprovementEngine(session)
        active_rules = await improvement_engine.get_active_rules(strategy_id)
        return [
            ImprovementRuleCheck(
                id=r.id,
                rule_type=r.rule_type,
                pattern_name=r.pattern_name,
                condition_json=r.condition_json or {},
                description=r.description,
            )
            for r in active_rules
        ]

    async def _scan_for_signals(
        self,
        session: AsyncSession,
        instruments_data: dict[str, dict[str, list[Candle]]],
    ) -> None:
        """Escanea señales para cada estrategia habilitada."""
        total_trades = 0

        for strategy_id, config in STRATEGIES.items():
            if not config.enabled:
                continue

            try:
                # Cargar improvement rules
                improvement_engine = ImprovementEngine(session)
                active_rules = await improvement_engine.get_active_rules(strategy_id)
                rule_checks = [
                    ImprovementRuleCheck(
                        id=r.id,
                        rule_type=r.rule_type,
                        pattern_name=r.pattern_name,
                        condition_json=r.condition_json or {},
                        description=r.description,
                    )
                    for r in active_rules
                ]

                # Generar señales
                generator = ForexSignalGenerator(config, rule_checks)
                signals = generator.generate_signals(instruments_data)

                # Ejecutar cada señal
                for signal in signals:
                    traded = await self._execute_signal(session, signal, strategy_id)
                    if traded:
                        total_trades += 1

                # Verificar ciclo de mejora y aprendizaje
                await self._check_learning(session, strategy_id, improvement_engine)

            except Exception:
                log.exception("Error en estrategia %s", strategy_id)

        if total_trades > 0:
            log.info("Total trades ejecutados este ciclo: %d", total_trades)

    async def _execute_signal(
        self,
        session: AsyncSession,
        signal: ForexSignal,
        strategy_id: str,
    ) -> bool:
        """Ejecuta una señal: verifica riesgo, coloca orden en OANDA, registra en DB."""

        # 1. Obtener estado de la cuenta del broker
        try:
            account = await self._broker.get_account()
        except Exception:
            log.exception("Error obteniendo cuenta del broker")
            return False

        # 2. Verificar límites
        open_positions = await self._broker.get_positions()
        strategy_config = STRATEGIES[strategy_id]

        if len(open_positions) >= strategy_config.max_concurrent_positions:
            log.info(
                "[%s] Máximo de posiciones alcanzado (%d/%d)",
                strategy_id, len(open_positions), strategy_config.max_concurrent_positions,
            )
            return False

        # 3. Verificar spread
        try:
            price = await self._broker.get_price(signal.instrument)
            if not is_spread_acceptable(signal.instrument, price.spread):
                return False
        except Exception:
            log.exception("Error obteniendo precio de %s", signal.instrument)
            return False

        # 4. Obtener AgentState para tracking + stepped compound
        state = await self._ensure_state(session, strategy_id)

        # 5. Calcular position size con riesgo escalonado (stepped compound)
        # Base capital = monto sobre el cual se calcula el 1% de riesgo.
        # Solo sube cuando el balance alcanza +50% sobre la base.
        base_capital = state.base_capital_usd or account.balance
        risk_base, next_threshold = get_stepped_risk_base(
            account.balance, base_capital,
        )

        # Actualizar si subió de nivel
        if risk_base != base_capital:
            state.base_capital_usd = risk_base
            state.next_threshold_usd = next_threshold
            log.info(
                "[%s] Base capital actualizado: $%.2f → $%.2f (next: $%.2f)",
                strategy_id, base_capital, risk_base, next_threshold,
            )
        elif state.base_capital_usd is None:
            # Inicializar base capital con balance actual del broker
            state.base_capital_usd = account.balance
            state.next_threshold_usd = next_threshold
            log.info(
                "[%s] Base capital inicializado: $%.2f (next: $%.2f)",
                strategy_id, account.balance, next_threshold,
            )

        stop_distance = abs(signal.entry_price - signal.stop_price)
        units = calculate_position_size(
            instrument=signal.instrument,
            account_balance=risk_base,
            risk_pct=strategy_config.risk_per_trade_pct,
            stop_distance_price=stop_distance,
            current_price=price.mid,
        )

        if units <= 0:
            return False

        # Ajustar signo según dirección
        if signal.direction == "SHORT":
            units = -units

        # 5. Colocar orden en OANDA
        order_result = await self._broker.place_market_order(
            instrument=signal.instrument,
            units=units,
            stop_loss=signal.stop_price,
            take_profit=signal.tp1_price,
        )

        if not order_result.success:
            log.warning(
                "[%s] Orden rechazada para %s: %s",
                strategy_id, signal.instrument, order_result.error,
            )
            return False

        # 6. Registrar señal en DB
        db_signal = Signal(
            strategy_id=strategy_id,
            market_id=f"oanda:{signal.instrument}",
            symbol=signal.instrument,
            estimated_value=0,
            market_price=order_result.fill_price or signal.entry_price,
            deviation_pct=0,
            direction="BUY" if signal.direction == "LONG" else "SELL",
            confidence=signal.confidence,
            take_profit_pct=signal.risk_reward_ratio * stop_distance / signal.entry_price if signal.entry_price > 0 else 0,
            stop_loss_pct=stop_distance / signal.entry_price if signal.entry_price > 0 else 0,
            llm_model=f"rule:{signal.pattern_type}",
            llm_prompt_hash="",
            llm_response_summary=f"Patrón {signal.pattern_type} en {signal.instrument}",
            data_sources_used=["oanda_h1", "oanda_h4", f"oanda_{signal.entry_timeframe.lower()}", signal.pattern_type],
        )
        session.add(db_signal)
        await session.flush()

        # 7. Calcular datos técnicos de entrada
        risk_amount = risk_base * strategy_config.risk_per_trade_pct

        # EMA20 distance en ATR
        ema20_dist_atr = None
        if signal.pullback_result and hasattr(signal.pullback_result, "distance_to_ema20_atr"):
            ema20_dist_atr = signal.pullback_result.distance_to_ema20_atr

        # SMA200 distance en ATR
        sma200_dist_atr = None
        if signal.market_state_h1 and signal.market_state_h1.atr14 > 0:
            sma200_dist_atr = abs(
                signal.market_state_h1.price - signal.market_state_h1.sma200
            ) / signal.market_state_h1.atr14

        # Candle body/wick ratios
        candle_body_pct = None
        candle_upper_wick_pct = None
        candle_lower_wick_pct = None
        if signal.entry_candle:
            c = signal.entry_candle
            rng = c.high - c.low
            if rng > 0:
                candle_body_pct = abs(c.close - c.open) / rng
                candle_upper_wick_pct = (c.high - max(c.open, c.close)) / rng
                candle_lower_wick_pct = (min(c.open, c.close) - c.low) / rng

        # ATR14 y retrace %
        entry_atr14 = signal.market_state_h1.atr14 if signal.market_state_h1 else None
        entry_retrace_pct = None
        if signal.pullback_result and hasattr(signal.pullback_result, "retrace_pct"):
            entry_retrace_pct = signal.pullback_result.retrace_pct

        # 8. Registrar trade en DB
        trade = Trade(
            strategy_id=strategy_id,
            signal_id=db_signal.id,
            market_id=f"oanda:{signal.instrument}",
            symbol=signal.instrument,
            instrument=signal.instrument,
            direction="BUY" if signal.direction == "LONG" else "SELL",
            size_usd=abs(units) * (order_result.fill_price or signal.entry_price),
            quantity=abs(units),
            entry_price=order_result.fill_price or signal.entry_price,
            take_profit_price=signal.tp1_price,
            stop_loss_price=signal.stop_price,
            initial_stop_price=signal.stop_price,
            original_size_usd=abs(units) * (order_result.fill_price or signal.entry_price),
            pattern_name=signal.pattern_type,
            broker_trade_id=order_result.trade_id,
            risk_amount_usd=risk_amount,
            risk_reward_ratio=signal.risk_reward_ratio,
            stop_distance_pips=stop_distance,
            timeframe_entry=signal.entry_timeframe,
            context_timeframe="H4",
            market_state_json=signal.market_state_h1.to_dict(),
            status="OPEN",
            is_simulation=settings.oanda_environment == "practice",
            entry_ema20_distance_atr=ema20_dist_atr,
            entry_sma200_distance_atr=sma200_dist_atr,
            entry_candle_body_pct=candle_body_pct,
            entry_candle_upper_wick_pct=candle_upper_wick_pct,
            entry_candle_lower_wick_pct=candle_lower_wick_pct,
            entry_atr14=entry_atr14,
            entry_retrace_pct=entry_retrace_pct,
        )
        session.add(trade)
        await session.flush()

        # 8. Bitácora
        bitacora = Bitacora(
            trade_id=trade.id,
            strategy_id=strategy_id,
            symbol=signal.instrument,
            direction=trade.direction,
            entry_reasoning=(
                f"Patrón {signal.pattern_type} en pullback a EMA20. "
                f"R:R={signal.risk_reward_ratio:.1f}. "
                f"Tendencia H1: {signal.market_state_h1.trend_state}. "
                f"8/8 filtros de contexto pasados."
            ),
            market_context=signal.market_state_h1.to_dict(),
            entry_price=trade.entry_price,
            entry_time=datetime.now(timezone.utc),
        )
        session.add(bitacora)

        # 9. Actualizar AgentState (ya obtenido en paso 4)
        state.positions_open += 1
        state.trades_executed_total += 1
        state.last_trade_at = datetime.now(timezone.utc)
        state.last_cycle_at = datetime.now(timezone.utc)

        # Sync broker balance
        state.broker_balance = account.balance
        state.broker_equity = account.equity
        state.last_broker_sync_at = datetime.now(timezone.utc)

        log.info(
            "[%s] ✓ Trade ejecutado: %s %s %s | Entry=%.5f | SL=%.5f | TP=%.5f | R:R=%.1f | Units=%d",
            strategy_id,
            signal.direction,
            signal.instrument,
            signal.pattern_type,
            trade.entry_price,
            trade.stop_loss_price,
            trade.take_profit_price,
            signal.risk_reward_ratio,
            abs(units),
        )

        # Notificar por Telegram
        try:
            await self._notifier.send(
                f"📊 Trade {signal.direction} {signal.instrument}\n"
                f"Patrón: {signal.pattern_type}\n"
                f"Entry: {trade.entry_price:.5f}\n"
                f"SL: {trade.stop_loss_price:.5f}\n"
                f"TP: {trade.take_profit_price:.5f}\n"
                f"R:R: {signal.risk_reward_ratio:.1f}"
            )
        except Exception:
            pass  # No bloquear por fallo de notificación

        return True

    async def _manage_positions(self, session: AsyncSession) -> None:
        """Gestiona posiciones abiertas: break-even, parciales, trailing, sync."""
        try:
            broker_positions = await self._broker.get_positions()
        except Exception:
            log.exception("Error obteniendo posiciones del broker")
            return

        # Obtener trades abiertos de la DB
        result = await session.execute(
            select(Trade).where(Trade.status == "OPEN", Trade.broker_trade_id.isnot(None))
        )
        db_trades = {t.broker_trade_id: t for t in result.scalars().all()}

        # Reconciliar: posiciones en broker que ya cerraron
        broker_trade_ids = {p.trade_id for p in broker_positions}
        for broker_id, db_trade in db_trades.items():
            if broker_id not in broker_trade_ids:
                # Trade cerrado en broker (TP/SL hit) — sincronizar
                await self._sync_closed_trade(session, db_trade)

        # Para posiciones abiertas: gestionar break-even y trailing
        for position in broker_positions:
            if position.trade_id not in db_trades:
                # Adoptar posición huérfana del broker
                db_trade = await self._adopt_broker_position(session, position)
                if db_trade:
                    await self._manage_single_position(session, db_trade, position)
                continue

            db_trade = db_trades[position.trade_id]
            await self._manage_single_position(session, db_trade, position)

    async def _manage_single_position(
        self,
        _session: AsyncSession,
        trade: Trade,
        position,
    ) -> None:
        """Gestiona una posición individual: break-even, parciales."""
        entry = trade.entry_price
        initial_stop = trade.initial_stop_price or trade.stop_loss_price
        stop_distance = abs(entry - initial_stop)

        if stop_distance <= 0:
            return

        # Break-even at 1R
        if trade.partial_exits == 0:
            current_price_vs_entry = (
                (position.unrealized_pnl > 0 and abs(position.unrealized_pnl) / abs(position.units) >= stop_distance)
                if position.units != 0 else False
            )

            if current_price_vs_entry and position.stop_loss != entry:
                # Mover stop a break-even
                result = await self._broker.modify_trade(
                    trade_id=position.trade_id,
                    stop_loss=entry,
                )
                if result.success:
                    trade.stop_loss_price = entry
                    log.info(
                        "[%s] Break-even activado para %s %s",
                        trade.strategy_id, trade.direction, trade.instrument,
                    )

    async def _sync_closed_trade(self, session: AsyncSession, trade: Trade) -> None:
        """Sincroniza un trade que fue cerrado en el broker — calcula P&L."""
        trade.status = "CLOSED"
        trade.closed_at = datetime.now(timezone.utc)

        # Obtener precio actual para estimar exit_price
        try:
            price = await self._broker.get_price(trade.instrument)
            exit_price = price.mid
        except Exception:
            # Fallback: usar stop_loss o take_profit como estimación
            exit_price = trade.stop_loss_price or trade.entry_price

        trade.exit_price = exit_price

        # Calcular P&L
        if trade.direction == "BUY":
            pnl_raw = (exit_price - trade.entry_price) * trade.quantity
        else:  # SELL
            pnl_raw = (trade.entry_price - exit_price) * trade.quantity

        # Convertir de JPY a USD para pares con JPY como quote
        if trade.instrument and ("_JPY" in trade.instrument or "JPY" in trade.instrument):
            pnl_raw = pnl_raw / exit_price

        trade.pnl = pnl_raw

        # Determinar exit_reason por el precio de salida
        if trade.take_profit_price and trade.direction == "BUY" and exit_price >= trade.take_profit_price:
            trade.exit_reason = "TP"
        elif trade.take_profit_price and trade.direction == "SELL" and exit_price <= trade.take_profit_price:
            trade.exit_reason = "TP"
        elif trade.stop_loss_price and trade.direction == "BUY" and exit_price <= trade.stop_loss_price:
            trade.exit_reason = "SL"
        elif trade.stop_loss_price and trade.direction == "SELL" and exit_price >= trade.stop_loss_price:
            trade.exit_reason = "SL"
        else:
            trade.exit_reason = "BROKER"

        # Actualizar Bitacora correspondiente (exit data + pnl)
        result_bitacora = await session.execute(
            select(Bitacora).where(Bitacora.trade_id == trade.id)
        )
        bitacora_entry = result_bitacora.scalar_one_or_none()
        if bitacora_entry:
            bitacora_entry.exit_reason = trade.exit_reason
            bitacora_entry.exit_price = exit_price
            bitacora_entry.exit_time = datetime.now(timezone.utc)
            bitacora_entry.pnl = trade.pnl
            if trade.created_at:
                bitacora_entry.hold_duration_minutes = (
                    (datetime.now(timezone.utc) - trade.created_at).total_seconds() / 60
                )

        # Actualizar AgentState
        state = await self._ensure_state(session, trade.strategy_id)
        state.positions_open = max(0, state.positions_open - 1)
        state.total_pnl += trade.pnl or 0
        state.capital_usd += trade.pnl or 0

        if (trade.pnl or 0) >= 0:
            state.trades_won += 1
        else:
            state.trades_lost += 1

        # Actualizar peak capital
        if state.capital_usd > state.peak_capital_usd:
            state.peak_capital_usd = state.capital_usd

        # Registrar en ciclo de mejora
        try:
            improvement_engine = ImprovementEngine(session)
            cycle_ready = await improvement_engine.record_trade(trade)
            if cycle_ready:
                log.info(
                    "[%s] Ciclo de mejora listo para análisis",
                    trade.strategy_id,
                )
        except Exception:
            log.exception("[%s] Error registrando trade en ciclo de mejora", trade.strategy_id)

        log.info(
            "[%s] Trade %s %s cerrado: exit=%.5f pnl=%.2f reason=%s",
            trade.strategy_id, trade.direction, trade.instrument,
            exit_price, trade.pnl or 0, trade.exit_reason,
        )

    async def _adopt_broker_position(
        self, session: AsyncSession, position,
    ) -> Trade | None:
        """Crea un Trade local para una posición del broker sin registro en DB."""
        # Verificar que no exista ya (protección contra duplicados)
        result = await session.execute(
            select(Trade).where(Trade.broker_trade_id == position.trade_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # Determinar estrategia por dirección
        strategy_id = (
            "s1_pullback_20_up" if position.direction == "LONG"
            else "s2_pullback_20_down"
        )
        direction_db = "BUY" if position.direction == "LONG" else "SELL"
        size_usd = abs(position.units) * position.entry_price

        trade = Trade(
            strategy_id=strategy_id,
            market_id=f"capital:{position.instrument}",
            symbol=position.instrument,
            instrument=position.instrument,
            direction=direction_db,
            size_usd=size_usd,
            quantity=abs(position.units),
            entry_price=position.entry_price,
            stop_loss_price=position.stop_loss,
            initial_stop_price=position.stop_loss,
            take_profit_price=position.take_profit,
            original_size_usd=size_usd,
            broker_trade_id=position.trade_id,
            status="OPEN",
            is_simulation=False,
            pattern_name="adopted_from_broker",
        )
        session.add(trade)
        await session.flush()

        # Actualizar AgentState
        state = await self._ensure_state(session, strategy_id)
        state.positions_open += 1
        state.trades_executed_total += 1
        state.last_trade_at = datetime.now(timezone.utc)

        log.info(
            "[%s] Posición adoptada del broker: %s %s (deal=%s, entry=%.5f)",
            strategy_id, position.direction, position.instrument,
            position.trade_id, position.entry_price,
        )
        return trade

    async def _check_learning(
        self,
        session: AsyncSession,
        strategy_id: str,
        improvement_engine: ImprovementEngine,
    ) -> None:
        """Verifica si hay ciclos de mejora o reportes pendientes."""
        from app.db.models import ImprovementCycle

        try:
            # Verificar ciclos de mejora pendientes
            result = await session.execute(
                select(ImprovementCycle).where(
                    ImprovementCycle.strategy_id == strategy_id,
                    ImprovementCycle.status == "analyzing",
                )
            )
            analyzing = result.scalar_one_or_none()
            if analyzing:
                await improvement_engine.analyze_cycle(strategy_id)

            # Verificar si toca reporte de aprendizaje
            engine = BitacoraEngine(session, self._llm)
            if await engine.should_generate_report(strategy_id):
                log.info("[%s] Generando reporte de aprendizaje...", strategy_id)
                await engine.generate_lessons_batch(strategy_id)
                await engine.generate_learning_report(strategy_id)
        except Exception:
            log.exception("[%s] Error en sistema de aprendizaje", strategy_id)

    async def _ensure_state(self, session: AsyncSession, strategy_id: str) -> AgentState:
        """Obtiene o crea AgentState para una estrategia."""
        result = await session.execute(
            select(AgentState).where(AgentState.strategy_id == strategy_id)
        )
        state = result.scalar_one_or_none()
        if not state:
            config = STRATEGIES.get(strategy_id)
            initial = config.initial_capital_usd if config else 100_000.0
            state = AgentState(
                strategy_id=strategy_id,
                mode="SIMULATION" if settings.oanda_environment == "practice" else "LIVE",
                capital_usd=initial,
                peak_capital_usd=initial,
            )
            session.add(state)
            await session.flush()
        return state

    async def close(self) -> None:
        """Libera recursos."""
        await self._broker.close()
        await self._llm.close()
        await self._notifier.close()
