"""Motor de señales basado en reglas técnicas — reemplaza la generación LLM.

Combina patrones de velas + análisis de tendencia + reglas de mejora
para generar señales sin LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.signals.candle_patterns import CandlePatternDetector, SignalCandidate
from app.signals.trend_analysis import TrendAnalyzer
from app.strategies.registry import StrategyConfig

log = logging.getLogger(__name__)


@dataclass
class ImprovementRuleCheck:
    """Representación mínima de una regla de mejora para filtrar señales."""

    id: int
    rule_type: str         # "time_filter", "pattern_filter", "condition_filter", "volume_filter"
    pattern_name: str
    condition_json: dict   # Condiciones evaluables
    description: str


class RuleBasedSignalGenerator:
    """Genera señales combinando patrones de velas + tendencia + reglas de mejora.

    Flujo:
    1. Para cada símbolo, obtener tendencia (20/200 SMA del TF mayor)
    2. Detectar patrones en el TF de detección (5m o 15m)
    3. Filtrar por reglas de mejora permanentes
    4. Retornar señales aprobadas
    """

    def __init__(
        self,
        config: StrategyConfig,
        improvement_rules: list[ImprovementRuleCheck] | None = None,
    ) -> None:
        self._config = config
        self._rules = improvement_rules or []
        self._pattern_detector = CandlePatternDetector()
        self._trend_analyzer = TrendAnalyzer()

    def generate_signals(
        self,
        symbols_data: dict[str, dict[str, list]],
    ) -> list[SignalCandidate]:
        """Genera señales para todos los símbolos.

        Args:
            symbols_data: {
                "BTC/USDT": {
                    "5m": [[ts, O, H, L, C, V], ...],
                    "15m": [...],
                    "1h": [...],
                },
                ...
            }

        Returns:
            Lista de SignalCandidate aprobadas.
        """
        signal_type = self._config.signal_type
        all_signals: list[SignalCandidate] = []

        for symbol, timeframes in symbols_data.items():
            candles_1h = timeframes.get("1h", [])
            candles_15m = timeframes.get("15m", [])
            candles_5m = timeframes.get("5m", [])

            # 1. Determinar tendencia con TF mayor
            trend = self._trend_analyzer.get_trend_state(candles_1h)
            trend_state = trend.state

            # 2. Generar señales según el tipo de estrategia
            candidates = self._detect_for_strategy(
                signal_type, symbol, candles_5m, candles_15m, candles_1h, trend_state,
            )

            # 3. Filtrar por reglas de mejora
            for candidate in candidates:
                if self._passes_improvement_rules(candidate):
                    # Ajustar TP/SL a los rangos de la estrategia
                    self._clamp_tp_sl(candidate)
                    all_signals.append(candidate)
                else:
                    log.info(
                        "[%s] Señal %s %s rechazada por regla de mejora",
                        self._config.id, candidate.direction, candidate.symbol,
                    )

        log.info(
            "[%s] %d señales generadas por reglas técnicas",
            self._config.id, len(all_signals),
        )
        return all_signals

    def _detect_for_strategy(
        self,
        signal_type: str,
        symbol: str,
        candles_5m: list,
        candles_15m: list,
        candles_1h: list,
        trend_state: str,
    ) -> list[SignalCandidate]:
        """Detecta patrones según el tipo de señal de la estrategia."""

        if signal_type == "elephant_bar":
            candidates = []
            # Detectar en 5m y 15m
            for tf_candles in [candles_5m, candles_15m]:
                if tf_candles:
                    result = self._pattern_detector.detect_elephant_bar(
                        symbol, tf_candles, trend_state,
                    )
                    if result:
                        candidates.append(result)
            return candidates

        elif signal_type == "ignored_bar":
            candidates = []
            for tf_candles in [candles_5m, candles_15m]:
                if tf_candles:
                    result = self._pattern_detector.detect_ignored_bar(
                        symbol, tf_candles, trend_state,
                    )
                    if result:
                        candidates.append(result)
            return candidates

        elif signal_type == "sma_pullback":
            result = self._trend_analyzer.get_sma_pullback_signal(
                symbol, candles_1h, candles_15m,
            )
            if result:
                return [SignalCandidate(
                    symbol=result["symbol"],
                    direction=result["direction"],
                    pattern_name=result["pattern_name"],
                    confidence=result["confidence"],
                    entry_price=result["entry_price"],
                    stop_price=result["stop_price"],
                    tp_price=result["tp_price"],
                    deviation_pct=abs(result["entry_price"] - result["sma20"]) / result["sma20"] * 100 if result["sma20"] > 0 else 0,
                    rationale=result["rationale"],
                )]
            return []

        elif signal_type == "all_oliver":
            # Detectar todos los patrones (para testing)
            candidates = []
            for tf_candles in [candles_5m, candles_15m]:
                if tf_candles:
                    candidates.extend(
                        self._pattern_detector.detect_all(symbol, tf_candles, trend_state)
                    )
            # También SMA pullback
            sma_result = self._trend_analyzer.get_sma_pullback_signal(
                symbol, candles_1h, candles_15m,
            )
            if sma_result:
                candidates.append(SignalCandidate(
                    symbol=sma_result["symbol"],
                    direction=sma_result["direction"],
                    pattern_name=sma_result["pattern_name"],
                    confidence=sma_result["confidence"],
                    entry_price=sma_result["entry_price"],
                    stop_price=sma_result["stop_price"],
                    tp_price=sma_result["tp_price"],
                    deviation_pct=0,
                    rationale=sma_result["rationale"],
                ))
            return candidates

        elif signal_type == "custom_rules":
            # Placeholder para Andrés Valdez — se implementa después
            return []

        else:
            log.warning("signal_type desconocido: %s", signal_type)
            return []

    def _passes_improvement_rules(self, signal: SignalCandidate) -> bool:
        """Verifica que la señal no viole ninguna regla de mejora permanente."""
        from datetime import datetime, timezone

        for rule in self._rules:
            condition = rule.condition_json
            if not condition:
                continue

            rule_type = rule.rule_type

            if rule_type == "time_filter":
                forbidden_hours = condition.get("forbidden_hours", [])
                current_hour = datetime.now(timezone.utc).hour
                if current_hour in forbidden_hours:
                    log.debug(
                        "Regla #%d rechaza señal: hora %d prohibida (%s)",
                        rule.id, current_hour, rule.description,
                    )
                    return False

            elif rule_type == "pattern_filter":
                forbidden_patterns = condition.get("forbidden_patterns", [])
                if signal.pattern_name in forbidden_patterns:
                    log.debug(
                        "Regla #%d rechaza señal: patrón %s prohibido (%s)",
                        rule.id, signal.pattern_name, rule.description,
                    )
                    return False

            elif rule_type == "volume_filter":
                min_volume_ratio = condition.get("min_volume_ratio", 0)
                # No podemos verificar volumen aquí — se filtra antes
                # Este tipo se evaluará en el orchestrator
                pass

            elif rule_type == "condition_filter":
                # Filtros genéricos
                min_confidence = condition.get("min_confidence", 0)
                if signal.confidence < min_confidence:
                    log.debug(
                        "Regla #%d rechaza señal: confianza %.2f < %.2f (%s)",
                        rule.id, signal.confidence, min_confidence, rule.description,
                    )
                    return False

                forbidden_symbols = condition.get("forbidden_symbols", [])
                if signal.symbol in forbidden_symbols:
                    return False

                min_body_ratio = condition.get("min_body_ratio", 0)
                # Este filtro se aplica en el detector directamente
                pass

        return True

    def _clamp_tp_sl(self, signal: SignalCandidate) -> None:
        """Ajusta TP/SL al rango permitido por la estrategia."""
        config = self._config
        price = signal.entry_price
        if price <= 0:
            return

        if signal.direction == "BUY":
            actual_tp_pct = (signal.tp_price - price) / price
            actual_sl_pct = (price - signal.stop_price) / price
        else:
            actual_tp_pct = (price - signal.tp_price) / price
            actual_sl_pct = (signal.stop_price - price) / price

        # Clamp TP
        tp_pct = max(config.tp_min, min(actual_tp_pct, config.tp_max))
        # Clamp SL
        sl_pct = max(config.sl_min, min(actual_sl_pct, config.sl_max))

        # Recalcular precios
        if signal.direction == "BUY":
            signal.tp_price = price * (1 + tp_pct)
            signal.stop_price = price * (1 - sl_pct)
        else:
            signal.tp_price = price * (1 - tp_pct)
            signal.stop_price = price * (1 + sl_pct)
