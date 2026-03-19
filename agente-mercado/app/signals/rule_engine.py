"""Pipeline de señales Forex — Oliver Vélez S1/S2.

Arquitectura multi-timeframe:
- Fase 1 (cada 15 min): H1/H4 → MarketState → 8 filtros de contexto → cachear
- Fase 2 (cada 1 min): M1 → pullback + patrón → señal → ejecución

Flujo legacy (generate_signals) sigue funcionando como wrapper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.broker.models import Candle
from app.forex.instruments import get_buffer_price
from app.signals.context_filters import ContextFilterEngine, FilterResult
from app.signals.entry_patterns import EntryPatternDetector, PatternResult
from app.signals.market_state import MarketState, MarketStateAnalyzer
from app.signals.pullback_detector import PullbackDetector, PullbackResult
from app.strategies.registry import StrategyConfig

log = logging.getLogger(__name__)


@dataclass
class ContextResult:
    """Resultado de la fase 1: contexto H1/H4 aprobado para un instrumento."""

    instrument: str
    direction: str
    market_state_h1: MarketState
    market_state_h4: MarketState | None
    filter_result: FilterResult
    timestamp: datetime


@dataclass
class ForexSignal:
    """Señal de trading generada por el pipeline."""

    instrument: str
    strategy_id: str
    direction: str  # "LONG" | "SHORT"
    pattern_type: str
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float | None
    risk_reward_ratio: float
    confidence: float

    # Context snapshot
    market_state_h1: MarketState
    market_state_h4: MarketState | None
    filter_result: FilterResult
    pullback_result: PullbackResult

    # Vela de entrada (para datos técnicos en improvement engine)
    entry_candle: Candle | None = None

    # Timeframe de entrada (H1 legacy, M1 nuevo)
    entry_timeframe: str = "H1"

    created_at: datetime = None  # type: ignore

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@dataclass
class ImprovementRuleCheck:
    """Regla de mejora para filtrar señales (permanente e irrevocable)."""

    id: int
    rule_type: str
    pattern_name: str
    condition_json: dict
    description: str


class ForexSignalGenerator:
    """Genera señales S1/S2 según el Plan de Trading de Oliver Vélez.

    Reemplaza al antiguo RuleBasedSignalGenerator.
    """

    def __init__(
        self,
        config: StrategyConfig,
        improvement_rules: list[ImprovementRuleCheck] | None = None,
    ) -> None:
        self._config = config
        self._rules = improvement_rules or []
        self._state_analyzer = MarketStateAnalyzer()
        self._filter_engine = ContextFilterEngine()
        self._pattern_detector = EntryPatternDetector()
        # Pullback detector H1 (umbrales estándar)
        self._pullback_detector = PullbackDetector()
        # Pullback detector M5 (umbrales más permisivos)
        self._pullback_detector_m5 = PullbackDetector(
            min_retrace_pct=config.m5_min_retrace_pct,
            ema20_zone_atr_mult=config.m5_ema20_zone_atr_mult,
        )

    def generate_signals(
        self,
        instruments_data: dict[str, dict[str, list[Candle]]],
    ) -> list[ForexSignal]:
        """Genera señales para todos los instrumentos.

        Args:
            instruments_data: {
                "EUR_USD": {
                    "H1": [Candle, ...],
                    "H4": [Candle, ...],
                },
                ...
            }

        Returns:
            Lista de ForexSignal aprobadas.
        """
        direction = self._config.direction
        all_signals: list[ForexSignal] = []

        for instrument, timeframes in instruments_data.items():
            candles_h1 = timeframes.get("H1", [])
            candles_h4 = timeframes.get("H4", [])

            signal = self._analyze_instrument(
                instrument, candles_h1, candles_h4, direction,
            )
            if signal:
                all_signals.append(signal)

        if all_signals:
            log.info(
                "[%s] %d señales generadas: %s",
                self._config.id,
                len(all_signals),
                ", ".join(f"{s.instrument} {s.pattern_type}" for s in all_signals),
            )

        return all_signals

    # ── Fase 1: Contexto H1/H4 ────────────────────────────────

    def check_context(
        self,
        instruments_data: dict[str, dict[str, list[Candle]]],
    ) -> dict[str, ContextResult]:
        """Fase 1: Analiza H1/H4 y corre los 8 filtros de contexto.

        Retorna dict de instrumentos que pasaron todos los filtros.
        Solo se ejecuta cada 15 min.
        """
        direction = self._config.direction
        results: dict[str, ContextResult] = {}

        for instrument, timeframes in instruments_data.items():
            candles_h1 = timeframes.get("H1", [])
            candles_h4 = timeframes.get("H4", [])

            # MarketState H1
            state_h1 = self._state_analyzer.analyze(instrument, "H1", candles_h1)
            if state_h1 is None:
                continue

            # MarketState H4
            state_h4 = None
            if candles_h4:
                state_h4 = self._state_analyzer.analyze(instrument, "H4", candles_h4)

            # 8 filtros de contexto
            filter_result = self._filter_engine.check_all_filters(
                state_h1, state_h4, direction,
            )
            if not filter_result.passed:
                log.debug(
                    "[%s] %s contexto NO pasa: %s",
                    self._config.id, instrument,
                    ", ".join(filter_result.failed_filters),
                )
                continue

            log.info(
                "[%s] %s contexto OK (%d/8 filtros)",
                self._config.id, instrument,
                len(filter_result.passed_filters),
            )

            results[instrument] = ContextResult(
                instrument=instrument,
                direction=direction,
                market_state_h1=state_h1,
                market_state_h4=state_h4,
                filter_result=filter_result,
                timestamp=datetime.now(timezone.utc),
            )

        return results

    # ── Fase 2: Entradas en M1 ─────────────────────────────────

    def scan_entries(
        self,
        context_results: dict[str, ContextResult],
        m5_data: dict[str, list[Candle]],
    ) -> list[ForexSignal]:
        """Fase 2: Busca pullback + patrón en timeframe de entrada para instrumentos listos.

        Solo se llama para instrumentos que ya pasaron check_context().
        Se ejecuta cada 1 min.

        Args:
            context_results: Resultado cacheado de check_context()
            m5_data: {"EUR_USD": [Candle, ...], ...} (M1 o M5 según config)
        """
        direction = self._config.direction
        signals: list[ForexSignal] = []

        for instrument, ctx in context_results.items():
            candles_m5 = m5_data.get(instrument, [])
            if not candles_m5:
                continue

            # MarketState M5 (sin SMA200)
            state_m5 = self._state_analyzer.analyze(
                instrument, "M5", candles_m5, require_sma200=False,
            )
            if state_m5 is None:
                continue

            # Pullback en M5 (umbrales permisivos)
            pullback = self._pullback_detector_m5.detect(state_m5, direction)
            if not pullback.is_valid:
                continue

            # Patrón de entrada en últimas 5 velas M5
            recent_candles = candles_m5[-5:]
            patterns = self._pattern_detector.detect_all(recent_candles, direction)
            if not patterns:
                continue

            best_pattern = max(patterns, key=lambda p: p.confidence)

            # Construir señal (usa state_h1 del contexto para swing levels)
            buffer = get_buffer_price(instrument)
            signal = self._build_signal(
                instrument, direction, best_pattern,
                ctx.market_state_h1, ctx.market_state_h4,
                ctx.filter_result, pullback, buffer,
            )
            if signal is None:
                continue

            signal.entry_timeframe = self._config.entry_timeframe
            signal.entry_candle = candles_m5[-1] if candles_m5 else None

            # Improvement rules
            if not self._passes_improvement_rules(signal):
                log.info(
                    "[%s] Señal M5 %s %s rechazada por regla de mejora",
                    self._config.id, direction, instrument,
                )
                continue

            log.info(
                "[%s] SEÑAL M5 %s %s — %s entry=%.5f stop=%.5f tp1=%.5f",
                self._config.id, direction, instrument, best_pattern.pattern_type,
                signal.entry_price, signal.stop_price, signal.tp1_price,
            )
            signals.append(signal)

        return signals

    # ── Legacy: análisis completo en H1 ────────────────────────

    def _analyze_instrument(
        self,
        instrument: str,
        candles_h1: list[Candle],
        candles_h4: list[Candle],
        direction: str,
    ) -> ForexSignal | None:
        """Analiza un instrumento y genera señal si cumple todas las condiciones."""

        # 1. Construir MarketState
        state_h1 = self._state_analyzer.analyze(instrument, "H1", candles_h1)
        if state_h1 is None:
            return None

        state_h4 = None
        if candles_h4:
            state_h4 = self._state_analyzer.analyze(instrument, "H4", candles_h4)

        # 2. Filtros de contexto (8 obligatorios)
        filter_result = self._filter_engine.check_all_filters(state_h1, state_h4, direction)
        if not filter_result.passed:
            return None

        # 3. Detectar pullback a EMA20
        pullback = self._pullback_detector.detect(state_h1, direction)
        if not pullback.is_valid:
            return None

        # 4. Buscar patrón de entrada en últimas velas H1
        recent_candles = candles_h1[-5:]  # Últimas 5 velas para análisis
        patterns = self._pattern_detector.detect_all(recent_candles, direction)
        if not patterns:
            return None

        # Tomar el patrón con mayor confianza
        best_pattern = max(patterns, key=lambda p: p.confidence)

        # 5. Calcular entry, stop y TP con buffer
        buffer = get_buffer_price(instrument)
        signal = self._build_signal(
            instrument, direction, best_pattern, state_h1, state_h4,
            filter_result, pullback, buffer,
        )

        if signal is None:
            return None

        signal.entry_candle = candles_h1[-1] if candles_h1 else None

        # 6. Filtrar por improvement rules
        if not self._passes_improvement_rules(signal):
            log.info(
                "[%s] Señal %s %s rechazada por regla de mejora",
                self._config.id, direction, instrument,
            )
            return None

        return signal

    def _build_signal(
        self,
        instrument: str,
        direction: str,
        pattern: PatternResult,
        state_h1: MarketState,
        state_h4: MarketState | None,
        filter_result: FilterResult,
        pullback: PullbackResult,
        buffer: float,
    ) -> ForexSignal | None:
        """Construye la señal con cálculos de entry/stop/TP y validación R:R."""

        if direction == "LONG":
            entry = pattern.pattern_high + buffer
            stop = pattern.pattern_low - buffer
            stop_distance = entry - stop

            if stop_distance <= 0:
                return None

            # TP1 = 2R (mínimo)
            tp1 = entry + (stop_distance * self._config.min_risk_reward)
            # TP2 = swing high anterior o 3R
            tp2 = max(state_h1.last_swing_high, entry + stop_distance * 3)

        else:  # SHORT
            entry = pattern.pattern_low - buffer
            stop = pattern.pattern_high + buffer
            stop_distance = stop - entry

            if stop_distance <= 0:
                return None

            tp1 = entry - (stop_distance * self._config.min_risk_reward)
            tp2 = min(state_h1.last_swing_low, entry - stop_distance * 3)

        # Verificar R:R
        rr = (abs(entry - tp1)) / stop_distance if stop_distance > 0 else 0
        if rr < self._config.min_risk_reward:
            log.debug(
                "R:R insuficiente para %s: %.2f (mín: %.1f)",
                instrument, rr, self._config.min_risk_reward,
            )
            return None

        return ForexSignal(
            instrument=instrument,
            strategy_id=self._config.id,
            direction=direction,
            pattern_type=pattern.pattern_type,
            entry_price=entry,
            stop_price=stop,
            tp1_price=tp1,
            tp2_price=tp2,
            risk_reward_ratio=rr,
            confidence=pattern.confidence,
            market_state_h1=state_h1,
            market_state_h4=state_h4,
            filter_result=filter_result,
            pullback_result=pullback,
        )

    def _passes_improvement_rules(self, signal: ForexSignal) -> bool:
        """Verifica que la señal no viole reglas de mejora permanentes."""
        for rule in self._rules:
            condition = rule.condition_json
            if not condition:
                continue

            if rule.rule_type == "time_filter":
                forbidden_hours = condition.get("forbidden_hours", [])
                current_hour = datetime.now(timezone.utc).hour
                if current_hour in forbidden_hours:
                    return False

            elif rule.rule_type == "pattern_filter":
                forbidden_patterns = condition.get("forbidden_patterns", [])
                if signal.pattern_type in forbidden_patterns:
                    return False

            elif rule.rule_type == "condition_filter":
                min_confidence = condition.get("min_confidence", 0)
                if signal.confidence < min_confidence:
                    return False

                forbidden_instruments = condition.get("forbidden_instruments", [])
                if signal.instrument in forbidden_instruments:
                    return False

            elif rule.rule_type == "session_filter":
                forbidden_sessions = condition.get("forbidden_sessions", [])
                from app.forex.sessions import get_current_session
                if get_current_session() in forbidden_sessions:
                    return False

            elif rule.rule_type == "ema20_distance_filter":
                # Filtrar por distancia a EMA20 en múltiplos de ATR
                if signal.pullback_result:
                    dist = signal.pullback_result.distance_to_ema20_atr
                    min_dist = condition.get("min_ema20_distance_atr", 0)
                    max_dist = condition.get("max_ema20_distance_atr", float("inf"))
                    if dist < min_dist or dist > max_dist:
                        return False

            elif rule.rule_type == "candle_quality_filter":
                # Filtrar por calidad de la vela de entrada
                if signal.entry_candle:
                    candle = signal.entry_candle
                    rng = candle.high - candle.low
                    if rng > 0:
                        body = abs(candle.close - candle.open)
                        body_pct = body / rng
                        min_body = condition.get("min_body_pct", 0)
                        if body_pct < min_body:
                            return False
                        max_upper_wick = condition.get("max_upper_wick_pct", 1.0)
                        upper_wick = (candle.high - max(candle.open, candle.close)) / rng
                        if upper_wick > max_upper_wick:
                            return False
                        max_lower_wick = condition.get("max_lower_wick_pct", 1.0)
                        lower_wick = (min(candle.open, candle.close) - candle.low) / rng
                        if lower_wick > max_lower_wick:
                            return False

            elif rule.rule_type == "sma200_distance_filter":
                # Filtrar por distancia a SMA200 en múltiplos de ATR
                if signal.market_state_h1 and signal.market_state_h1.atr14 > 0:
                    dist = abs(signal.market_state_h1.price - signal.market_state_h1.sma200) / signal.market_state_h1.atr14
                    min_dist = condition.get("min_sma200_distance_atr", 0)
                    max_dist = condition.get("max_sma200_distance_atr", float("inf"))
                    if dist < min_dist or dist > max_dist:
                        return False

        return True
