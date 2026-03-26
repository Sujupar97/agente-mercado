"""Motor de señales SMC — Estrategia S3 El Sensei.

Pipeline multi-timeframe:
1. BIAS macro: D1 → estructura + BOS/ChoCH → dirección del día
2. BIAS intraday: H4/H1 → confirmar alineación con macro
3. Entradas: M5 → Order Block + Liquidity Sweep + BOS confirmación
4. Gestión: SL debajo/encima del OB, TP en próximo nivel de liquidez
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.broker.models import Candle
from app.forex.instruments import get_buffer_price
from app.signals.market_state import MarketStateAnalyzer
from app.signals.rule_engine import ForexSignal, ImprovementRuleCheck
from app.signals.smc.fair_value_gaps import FVGDetector
from app.signals.smc.liquidity import LiquidityDetector
from app.signals.smc.order_blocks import OrderBlockDetector
from app.signals.smc.structure import MarketStructureAnalyzer
from app.strategies.registry import StrategyConfig

log = logging.getLogger(__name__)


class SMCSignalGenerator:
    """Genera señales S3 según Smart Money Concepts."""

    def __init__(
        self,
        config: StrategyConfig,
        improvement_rules: list[ImprovementRuleCheck] | None = None,
    ) -> None:
        self._config = config
        self._rules = improvement_rules or []
        self._structure = MarketStructureAnalyzer(swing_lookback=3)
        self._ob_detector = OrderBlockDetector()
        self._fvg_detector = FVGDetector()
        self._liq_detector = LiquidityDetector()
        self._state_analyzer = MarketStateAnalyzer()

    # ── Fase 1: BIAS Multi-Timeframe ─────────────────────────────

    def check_bias(
        self,
        instruments_data: dict[str, dict[str, list[Candle]]],
    ) -> dict[str, str]:
        """Determina BIAS para cada instrumento usando D1 > H4 > H1.

        Returns:
            {"EUR_USD": "BULLISH", "GBP_USD": "BEARISH", ...}
        """
        bias_results: dict[str, str] = {}

        for instrument, timeframes in instruments_data.items():
            candles_d1 = timeframes.get("D1", [])
            candles_h4 = timeframes.get("H4", [])
            candles_h1 = timeframes.get("H1", [])

            # BIAS jerárquico: D1 > H4 > H1
            bias_d1 = self._structure.get_bias(candles_d1) if len(candles_d1) >= 20 else "NEUTRAL"
            bias_h4 = self._structure.get_bias(candles_h4) if len(candles_h4) >= 20 else "NEUTRAL"
            bias_h1 = self._structure.get_bias(candles_h1) if len(candles_h1) >= 20 else "NEUTRAL"

            # BIAS final: D1 tiene prioridad, H4 y H1 confirman
            if bias_d1 != "NEUTRAL":
                # Si D1 tiene dirección, necesitamos al menos 1 confirmación
                confirmations = sum(1 for b in [bias_h4, bias_h1] if b == bias_d1)
                if confirmations >= 1:
                    final_bias = bias_d1
                else:
                    final_bias = "NEUTRAL"
            elif bias_h4 != "NEUTRAL":
                # Sin D1 claro, usar H4 + H1
                final_bias = bias_h4 if bias_h1 == bias_h4 else "NEUTRAL"
            else:
                final_bias = "NEUTRAL"

            bias_results[instrument] = final_bias
            log.info(
                "[%s] %s BIAS: D1=%s H4=%s H1=%s → %s",
                self._config.id, instrument, bias_d1, bias_h4, bias_h1, final_bias,
            )

        return bias_results

    # ── Fase 2: Entradas en M5 ──────────────────────────────────

    def scan_entries(
        self,
        bias_results: dict[str, str],
        entry_data: dict[str, list[Candle]],
        h1_data: dict[str, list[Candle]] | None = None,
    ) -> list[ForexSignal]:
        """Busca entradas en M5 alineadas con el BIAS.

        Pipeline por instrumento:
        1. Verificar BIAS no es NEUTRAL
        2. Analizar estructura en M5
        3. Buscar liquidity sweep reciente
        4. Identificar Order Block activo en dirección del BIAS
        5. Precio en/cerca del OB → señal
        """
        signals: list[ForexSignal] = []

        for instrument, bias in bias_results.items():
            if bias == "NEUTRAL":
                continue

            candles = entry_data.get(instrument, [])
            if len(candles) < 30:
                continue

            signal = self._analyze_instrument(instrument, bias, candles, h1_data)
            if signal:
                signals.append(signal)

        return signals

    def _analyze_instrument(
        self,
        instrument: str,
        bias: str,
        candles: list[Candle],
        h1_data: dict[str, list[Candle]] | None = None,
    ) -> ForexSignal | None:
        """Analiza un instrumento en M5 para encontrar entrada SMC."""
        direction = "LONG" if bias == "BULLISH" else "SHORT"

        # 1. Estructura en M5
        structure = self._structure.identify_structure(candles)
        if len(structure) < 3:
            log.debug("[%s] %s: estructura insuficiente en M5", self._config.id, instrument)
            return None

        # 2. Detectar rupturas de estructura
        breaks = self._structure.detect_breaks(candles, structure)
        if not breaks:
            log.info(
                "[%s] %s M5: sin BOS/ChoCH reciente",
                self._config.id, instrument,
            )
            return None

        # Verificar que el último break sea en la dirección del BIAS
        last_break = breaks[-1]
        if last_break.direction != bias:
            log.info(
                "[%s] %s M5: último break %s %s no alineado con BIAS %s",
                self._config.id, instrument, last_break.type, last_break.direction, bias,
            )
            return None

        # 3. Calcular ATR para referencias
        state_m5 = self._state_analyzer.analyze(
            instrument, "M5", candles, require_sma200=False,
        )
        atr = state_m5.atr14 if state_m5 else 0

        # 4. Buscar Order Block activo
        active_obs = self._ob_detector.get_active_order_blocks(candles, breaks)
        target_ob_type = "BULLISH_OB" if direction == "LONG" else "BEARISH_OB"
        relevant_obs = [ob for ob in active_obs if ob.type == target_ob_type]

        if not relevant_obs:
            log.info(
                "[%s] %s M5: BOS %s confirmado pero sin OB %s activo",
                self._config.id, instrument, bias, target_ob_type,
            )
            return None

        # Usar el OB más reciente
        best_ob = max(relevant_obs, key=lambda ob: ob.origin_index)

        # 5. Verificar que el precio está cerca del OB
        current_price = candles[-1].close
        if not self._price_near_ob(current_price, best_ob, atr):
            log.info(
                "[%s] %s M5: OB encontrado [%.5f-%.5f] pero precio %.5f no está cerca",
                self._config.id, instrument, best_ob.low, best_ob.high, current_price,
            )
            return None

        # 6. Buscar liquidity sweep (bonus, no obligatorio pero mejora la señal)
        liq_pools = self._liq_detector.find_liquidity_pools(candles, structure, atr)
        sweeps = self._liq_detector.detect_sweeps(candles, liq_pools, lookback=10)
        has_sweep = any(
            (s.type == "SELL_SIDE_SWEEP" and direction == "LONG") or
            (s.type == "BUY_SIDE_SWEEP" and direction == "SHORT")
            for s in sweeps
        )

        # 7. Construir señal
        buffer = get_buffer_price(instrument)
        signal = self._build_signal(
            instrument, direction, best_ob, candles, atr, buffer, has_sweep,
            h1_data.get(instrument) if h1_data else None,
        )

        if signal:
            log.info(
                "[%s] SEÑAL SMC %s %s — OB [%.5f-%.5f] BOS=%s sweep=%s entry=%.5f stop=%.5f tp1=%.5f",
                self._config.id, direction, instrument,
                best_ob.low, best_ob.high, last_break.type,
                has_sweep, signal.entry_price, signal.stop_price, signal.tp1_price,
            )

        return signal

    def _price_near_ob(self, price: float, ob, atr: float) -> bool:
        """Verifica que el precio esté dentro o muy cerca del Order Block."""
        if atr <= 0:
            return False

        if ob.type == "BULLISH_OB":
            # Precio debe estar dentro del OB o máximo 0.5 ATR por encima
            return price <= ob.high + atr * 0.5 and price >= ob.low - atr * 0.3
        else:
            # Precio debe estar dentro del OB o máximo 0.5 ATR por debajo
            return price >= ob.low - atr * 0.5 and price <= ob.high + atr * 0.3

    def _build_signal(
        self,
        instrument: str,
        direction: str,
        ob,
        candles: list[Candle],
        atr: float,
        buffer: float,
        has_sweep: bool,
        candles_h1: list[Candle] | None = None,
    ) -> ForexSignal | None:
        """Construye ForexSignal a partir de un Order Block."""
        from app.signals.context_filters import FilterResult
        from app.signals.pullback_detector import PullbackResult

        if direction == "LONG":
            entry = candles[-1].close + buffer
            stop = ob.low - buffer
            stop_distance = entry - stop
        else:
            entry = candles[-1].close - buffer
            stop = ob.high + buffer
            stop_distance = stop - entry

        if stop_distance <= 0:
            return None

        # TP1 = 2R mínimo
        min_rr = self._config.min_risk_reward
        if direction == "LONG":
            tp1 = entry + stop_distance * min_rr
            tp2 = entry + stop_distance * 3
        else:
            tp1 = entry - stop_distance * min_rr
            tp2 = entry - stop_distance * 3

        rr = abs(entry - tp1) / stop_distance if stop_distance > 0 else 0
        if rr < min_rr:
            return None

        # Confidence basado en factores
        confidence = 0.5
        if has_sweep:
            confidence += 0.2  # Sweep confirma
        confidence = min(confidence, 1.0)

        # Build MarketState H1 for the signal (needed by ForexSignal)
        state_h1 = None
        if candles_h1 and len(candles_h1) >= 200:
            state_h1 = self._state_analyzer.analyze(instrument, "H1", candles_h1)

        # Dummy filter/pullback results (SMC no usa estos filtros)
        filter_result = FilterResult(
            passed=True,
            passed_filters=["smc_bias_aligned", "smc_ob_found", "smc_bos_confirmed"],
            failed_filters=[],
            total_filters=3,
        )
        pullback_result = PullbackResult(
            is_valid=True,
            retrace_pct=0,
            distance_to_ema20=0,
            distance_to_ema20_atr=0,
        )

        return ForexSignal(
            instrument=instrument,
            strategy_id=self._config.id,
            direction=direction,
            pattern_type=f"SMC_OB_{'SWEEP_' if has_sweep else ''}{direction}",
            entry_price=entry,
            stop_price=stop,
            tp1_price=tp1,
            tp2_price=tp2,
            risk_reward_ratio=rr,
            confidence=confidence,
            market_state_h1=state_h1,
            market_state_h4=None,
            filter_result=filter_result,
            pullback_result=pullback_result,
            entry_candle=candles[-1],
            entry_timeframe=self._config.entry_timeframe,
        )
