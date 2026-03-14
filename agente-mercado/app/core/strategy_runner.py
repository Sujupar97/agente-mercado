"""Runner individual de estrategia — señales por reglas técnicas, sin LLM.

Flujo por ciclo:
1. Obtener AgentState
2. Verificar intervalo
3. Obtener datos OHLCV multi-timeframe
4. Cargar ImprovementRules activas
5. Generar señales con RuleBasedSignalGenerator (SIN LLM)
6. Risk check (RiskManager)
7. Ejecutar trades + crear bitácora
8. Registrar en ImprovementCycle
9. Si ciclo = 20 trades → analizar con LLM
10. Si 15+ trades cerrados → reporte de aprendizaje (LLM)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.ohlcv import OHLCVProvider
from app.db.models import AgentState, Bitacora, Signal, Trade
from app.learning.adaptive import AdaptiveFilter
from app.learning.bitacora_engine import BitacoraEngine
from app.learning.improvement_engine import ImprovementEngine
from app.llm.base import LLMClient
from app.llm.budget import LLMBudget
from app.notifications.telegram import TelegramNotifier
from app.risk.manager import RiskManager
from app.signals.candle_patterns import SignalCandidate
from app.signals.rule_engine import ImprovementRuleCheck, RuleBasedSignalGenerator
from app.strategies.registry import StrategyConfig
from app.trading.executor import OrderExecutor
from app.trading.position_scaler import PositionScaler

log = logging.getLogger(__name__)


class StrategyRunner:
    """Ejecuta una estrategia individual con señales basadas en reglas técnicas."""

    def __init__(
        self,
        config: StrategyConfig,
        llm: LLMClient,
        budget: LLMBudget,
        executor: OrderExecutor,
        notifier: TelegramNotifier,
        ohlcv: OHLCVProvider,
    ) -> None:
        self._config = config
        self._llm = llm
        self._budget = budget
        self._executor = executor
        self._notifier = notifier
        self._ohlcv = ohlcv
        self._scaler = PositionScaler()
        self._cycle_count = 0
        self._adjustments: list = []
        self._last_run: datetime | None = None

    @property
    def strategy_id(self) -> str:
        return self._config.id

    def should_run_this_cycle(self) -> bool:
        """Verifica si le toca ejecutar segun su intervalo."""
        if self._last_run is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self._last_run).total_seconds()
        return elapsed >= self._config.cycle_interval_minutes * 60

    async def run(
        self,
        top_symbols: list[str],
        session: AsyncSession,
        tickers_count: int,
    ) -> int:
        """Ejecuta un ciclo completo para esta estrategia.

        Args:
            top_symbols: Lista de símbolos pre-filtrados (ya viables).
            session: Sesión de BD.
            tickers_count: Total de tickers escaneados (para stats).

        Returns:
            Numero de trades ejecutados.
        """
        self._last_run = datetime.now(timezone.utc)
        config = self._config
        sid = self.strategy_id
        log.info("[%s] Iniciando ciclo #%d", sid, self._cycle_count + 1)

        # 1. Obtener o crear AgentState
        state = await self._ensure_state(session)
        if state.mode in ("SHUTDOWN", "PAUSED"):
            log.info("[%s] Modo %s — saltando ciclo", sid, state.mode)
            return 0

        is_simulation = state.mode == "SIMULATION"

        # 2. Filtros adaptativos (cada hora)
        filtered_symbols = list(top_symbols)
        if self._cycle_count % 12 == 0 and self._cycle_count > 0:
            adaptive = AdaptiveFilter(session, strategy_id=sid)
            self._adjustments = await adaptive.compute_adjustments()
            if self._adjustments:
                await adaptive.log_adjustments(self._adjustments)

        if self._adjustments:
            af = AdaptiveFilter(session, strategy_id=sid)
            blacklisted = af.get_blacklisted_symbols(self._adjustments)
            if blacklisted:
                before = len(filtered_symbols)
                filtered_symbols = [s for s in filtered_symbols if s not in blacklisted]
                log.info("[%s] Blacklist: %d → %d pares", sid, before, len(filtered_symbols))

        if not filtered_symbols:
            self._cycle_count += 1
            return 0

        # 3. Obtener datos OHLCV multi-timeframe
        symbols_data: dict[str, dict[str, list]] = {}
        for symbol in filtered_symbols[:30]:
            tf_data = await self._ohlcv.fetch_multi_timeframe(symbol, sid)
            if tf_data:
                symbols_data[symbol] = tf_data

        if not symbols_data:
            log.warning("[%s] Sin datos OHLCV disponibles", sid)
            self._cycle_count += 1
            return 0

        log.info("[%s] OHLCV obtenido para %d símbolos", sid, len(symbols_data))

        # 3b. Actualizar trailing stops de posiciones abiertas
        await self._update_trailing_stops(session, sid, symbols_data)

        # 4. Cargar reglas de mejora activas
        improvement_engine = ImprovementEngine(session)
        active_rules = await improvement_engine.get_active_rules(sid)
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

        if rule_checks:
            log.info("[%s] %d reglas de mejora activas", sid, len(rule_checks))

        # 5. Generar señales con RuleBasedSignalGenerator (SIN LLM)
        signal_gen = RuleBasedSignalGenerator(config, rule_checks)
        candidates = signal_gen.generate_signals(symbols_data)
        log.info("[%s] %d señales generadas por reglas técnicas", sid, len(candidates))

        if not candidates:
            self._cycle_count += 1
            state.markets_scanned_total += tickers_count
            state.last_cycle_at = datetime.now(timezone.utc)
            return 0

        # 6. Guardar señales en BD
        signal_ids: dict[str, int] = {}
        for sig in candidates:
            db_signal = Signal(
                strategy_id=sid,
                market_id=f"binance:{sig.symbol}",
                symbol=sig.symbol,
                estimated_value=0,
                market_price=sig.entry_price,
                deviation_pct=sig.deviation_pct,
                direction=sig.direction,
                confidence=sig.confidence,
                take_profit_pct=self._calc_tp_pct(sig),
                stop_loss_pct=self._calc_sl_pct(sig),
                llm_model=f"rule:{sig.pattern_name}",
                llm_prompt_hash="",
                llm_response_summary=sig.rationale[:500],
                data_sources_used=["ohlcv", sig.pattern_name],
            )
            session.add(db_signal)
            await session.flush()
            signal_ids[sig.symbol] = db_signal.id

        # 7. Position sizing + ejecución
        risk_mgr = RiskManager(session, strategy_id=sid)

        equity_result = await session.execute(
            select(sa_func.coalesce(sa_func.sum(Trade.size_usd), 0.0))
            .where(Trade.status == "OPEN", Trade.strategy_id == sid)
        )
        capital_in_positions = float(equity_result.scalar() or 0.0)
        equity = state.capital_usd + capital_in_positions

        trades_executed = 0
        for sig in candidates:
            tp_pct = self._calc_tp_pct(sig)
            sl_pct = self._calc_sl_pct(sig)

            pos_result = await risk_mgr.calculate_position(
                p_win=sig.confidence,
                take_profit_pct=tp_pct,
                stop_loss_pct=sl_pct,
                capital=equity,
            )
            if not pos_result.approved:
                continue

            ok, reason = await risk_mgr.check_all_limits(pos_result.size_usd)
            if not ok:
                continue

            if pos_result.size_usd > state.capital_usd:
                continue

            if is_simulation:
                trade = await self._execute_sim_trade(
                    session, state, sig, pos_result, signal_ids, sid,
                )
                if trade:
                    market_ctx = self._capture_market_context(sig.symbol, symbols_data)
                    bitacora = Bitacora(
                        trade_id=trade.id,
                        strategy_id=sid,
                        symbol=trade.symbol,
                        direction=trade.direction,
                        entry_reasoning=sig.rationale,
                        market_context=market_ctx,
                        entry_price=trade.entry_price,
                        entry_time=trade.created_at,
                    )
                    session.add(bitacora)
                    trades_executed += 1

        log.info("[%s] %d trades ejecutados", sid, trades_executed)

        # 8. Actualizar stats
        now = datetime.now(timezone.utc)
        state.markets_scanned_total += tickers_count
        state.trades_executed_total += trades_executed
        state.last_cycle_at = now
        if trades_executed > 0:
            state.last_trade_at = now

        # 9. Verificar ciclo de mejora y aprendizaje
        try:
            await self._check_improvement_cycle(session, sid, improvement_engine)

            engine = BitacoraEngine(session, self._llm)
            if await engine.should_generate_report(sid):
                log.info("[%s] Generando lecciones y reporte de aprendizaje...", sid)
                await engine.generate_lessons_batch(sid)
                report = await engine.generate_learning_report(sid)
                if report:
                    log.info("[%s] Reporte #%d generado", sid, report.report_number)
        except Exception:
            log.exception("[%s] Error en sistema de aprendizaje", sid)

        self._cycle_count += 1
        return trades_executed

    async def _check_improvement_cycle(
        self,
        session: AsyncSession,
        strategy_id: str,
        improvement_engine: ImprovementEngine,
    ) -> bool:
        """Verifica si hay ciclos de mejora pendientes de análisis."""
        from app.db.models import ImprovementCycle

        result = await session.execute(
            select(ImprovementCycle)
            .where(
                ImprovementCycle.strategy_id == strategy_id,
                ImprovementCycle.status == "analyzing",
            )
        )
        analyzing = result.scalar_one_or_none()
        if analyzing:
            rule = await improvement_engine.analyze_cycle(strategy_id)
            return rule is not None
        return False

    async def _execute_sim_trade(
        self, session, state, sig: SignalCandidate,
        pos_result, signal_ids: dict, sid: str,
    ) -> Trade | None:
        """Ejecuta un paper trade con precios reales."""
        try:
            from app.markets.crypto_exchange import CryptoExchangeProvider
            provider = CryptoExchangeProvider()
            exchange = provider._exchanges[0][1]
            ticker = await exchange.fetch_ticker(sig.symbol)
            current_price = ticker.get("last", 0)
            if current_price <= 0:
                return None

            quantity = pos_result.size_usd / current_price
            sim_fees = pos_result.size_usd * 0.001

            tp_pct = self._calc_tp_pct(sig)
            sl_pct = self._calc_sl_pct(sig)

            if sig.direction == "BUY":
                tp_price = current_price * (1 + tp_pct)
                sl_price = current_price * (1 - sl_pct)
            else:
                tp_price = current_price * (1 - tp_pct)
                sl_price = current_price * (1 + sl_pct)

            trade = Trade(
                strategy_id=sid,
                signal_id=signal_ids.get(sig.symbol),
                market_id=f"binance:{sig.symbol}",
                symbol=sig.symbol,
                direction=sig.direction,
                size_usd=pos_result.size_usd,
                quantity=quantity,
                entry_price=current_price,
                take_profit_price=tp_price,
                stop_loss_price=sl_price,
                initial_stop_price=sl_price,
                original_size_usd=pos_result.size_usd,
                pattern_name=sig.pattern_name,
                kelly_fraction=pos_result.kelly_adjusted,
                fees=sim_fees,
                status="OPEN",
                is_simulation=True,
            )
            session.add(trade)
            await session.flush()

            state.capital_usd -= pos_result.size_usd
            state.positions_open += 1

            log.info(
                "[%s] SIM Trade: %s %s [%s] %.6f @ $%.4f | Size=$%.2f",
                sid, sig.direction, sig.symbol, sig.pattern_name,
                quantity, current_price, pos_result.size_usd,
            )
            return trade
        except Exception:
            log.exception("[%s] Error en paper trade %s", sid, sig.symbol)
            return None

    async def _ensure_state(self, session: AsyncSession) -> AgentState:
        """Obtiene o crea AgentState para esta estrategia."""
        result = await session.execute(
            select(AgentState).where(AgentState.strategy_id == self.strategy_id)
        )
        state = result.scalar_one_or_none()
        if not state:
            state = AgentState(
                strategy_id=self.strategy_id,
                mode="SIMULATION",
                capital_usd=self._config.initial_capital_usd,
                peak_capital_usd=self._config.initial_capital_usd,
            )
            session.add(state)
            await session.flush()
            log.info("[%s] Estado creado: capital=$%.2f", self.strategy_id, state.capital_usd)
        return state

    def _calc_tp_pct(self, sig: SignalCandidate) -> float:
        """Calcula TP% basado en entry/tp price."""
        if sig.entry_price <= 0:
            return self._config.tp_min
        pct = abs(sig.tp_price - sig.entry_price) / sig.entry_price
        return max(self._config.tp_min, min(pct, self._config.tp_max))

    def _calc_sl_pct(self, sig: SignalCandidate) -> float:
        """Calcula SL% basado en entry/stop price."""
        if sig.entry_price <= 0:
            return self._config.sl_min
        pct = abs(sig.stop_price - sig.entry_price) / sig.entry_price
        return max(self._config.sl_min, min(pct, self._config.sl_max))

    async def _update_trailing_stops(
        self,
        session: AsyncSession,
        strategy_id: str,
        symbols_data: dict[str, dict[str, list]],
    ) -> None:
        """Actualiza trailing stops de posiciones abiertas usando datos OHLCV."""
        result = await session.execute(
            select(Trade).where(
                Trade.strategy_id == strategy_id,
                Trade.status == "OPEN",
            )
        )
        open_trades = result.scalars().all()
        if not open_trades:
            return

        updated = 0
        for trade in open_trades:
            if trade.symbol not in symbols_data:
                continue

            # Usar timeframe de detección (5m) para trailing stop
            tf_data = symbols_data[trade.symbol]
            candles = tf_data.get("5m") or tf_data.get("15m")
            if not candles or len(candles) < 2:
                continue

            new_stop = self._scaler.update_trailing_stop(trade, candles)
            if new_stop is not None:
                trade.trailing_stop_price = new_stop
                trade.stop_loss_price = new_stop
                updated += 1

        if updated:
            log.info("[%s] %d trailing stops actualizados", strategy_id, updated)

    def _capture_market_context(
        self, symbol: str, symbols_data: dict[str, dict[str, list]],
    ) -> dict:
        """Captura snapshot del mercado para la bitácora."""
        ctx: dict = {}
        if symbol in symbols_data:
            tf_data = symbols_data[symbol]
            if "1h" in tf_data and tf_data["1h"]:
                last_1h = tf_data["1h"][-1]
                ctx["price"] = last_1h[4]
                ctx["volume_1h"] = last_1h[5]
            if "5m" in tf_data and tf_data["5m"]:
                last_5m = tf_data["5m"][-1]
                ctx["price_5m"] = last_5m[4]
        return ctx
