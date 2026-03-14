"""Detectores de patrones de velas según Oliver Vélez.

Cada detector analiza velas OHLCV y retorna señales candidatas con:
- direction (BUY/SELL)
- entry_price, stop_price, tp_price
- confidence (0-1 basada en confluencia)
- pattern_name para la bitácora
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SignalCandidate:
    """Señal generada por un detector de patrones."""

    symbol: str
    direction: str          # "BUY" | "SELL"
    pattern_name: str       # "elephant_bar", "ignored_bar", etc.
    confidence: float       # 0.0 - 1.0
    entry_price: float      # Precio de entrada sugerido
    stop_price: float       # Stop loss
    tp_price: float         # Take profit
    deviation_pct: float    # Desviación estimada (para compatibilidad)
    rationale: str          # Explicación del patrón detectado


def _body_ratio(candle: list) -> float:
    """Calcula ratio cuerpo/rango de una vela. candle = [ts, O, H, L, C, V]."""
    o, h, l, c = candle[1], candle[2], candle[3], candle[4]
    rng = h - l
    if rng <= 0:
        return 0.0
    body = abs(c - o)
    return body / rng


def _is_bullish(candle: list) -> bool:
    return candle[4] > candle[1]  # close > open


def _is_bearish(candle: list) -> bool:
    return candle[4] < candle[1]  # close < open


def _avg_volume(candles: list, period: int = 20) -> float:
    vols = [c[5] for c in candles[-period:]]
    return sum(vols) / max(len(vols), 1)


class CandlePatternDetector:
    """Detecta patrones de velas de Oliver Vélez en datos OHLCV."""

    def detect_elephant_bar(
        self,
        symbol: str,
        candles: list,
        trend_state: str = "BULLISH",
    ) -> SignalCandidate | None:
        """Detecta vela elefante: cuerpo >= 70% del rango total.

        Reglas de Oliver Vélez:
        - Cuerpo >= 70% del rango (vela con convicción fuerte)
        - Volumen > promedio 20 períodos (confirma participación)
        - Entry: ruptura del máximo (alcista) o mínimo (bajista)
        - Stop: extremo opuesto de la vela elefante
        - Solo a favor de la tendencia (20/200 SMA)
        """
        if len(candles) < 21:
            return None

        last = candles[-1]
        o, h, l, c, vol = last[1], last[2], last[3], last[4], last[5]
        rng = h - l
        if rng <= 0:
            return None

        body = abs(c - o)
        ratio = body / rng

        if ratio < 0.70:
            return None

        avg_vol = _avg_volume(candles[:-1], 20)
        if avg_vol > 0 and vol < avg_vol:
            return None  # Volumen debe estar por encima del promedio

        bullish = _is_bullish(last)
        bearish = _is_bearish(last)

        # Solo operar a favor de la tendencia
        if bullish and trend_state == "BEARISH":
            return None
        if bearish and trend_state == "BULLISH":
            return None

        if bullish:
            direction = "BUY"
            entry = h  # Ruptura del máximo
            stop = l   # Extremo opuesto
            # TP: riesgo * 2 mínimo (risk/reward 1:2+)
            risk = entry - stop
            tp = entry + risk * 3  # Ganar 3 velas por 1 de pérdida
        elif bearish:
            direction = "SELL"
            entry = l
            stop = h
            risk = stop - entry
            tp = entry - risk * 3
        else:
            return None

        # Confidence basada en: body ratio + volumen
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0
        confidence = min(0.40 + ratio * 0.30 + min(vol_ratio - 1, 1) * 0.20, 0.95)

        # Deviation como % del precio
        deviation = abs(entry - c) / c * 100 if c > 0 else 0

        return SignalCandidate(
            symbol=symbol,
            direction=direction,
            pattern_name="elephant_bar",
            confidence=confidence,
            entry_price=entry,
            stop_price=stop,
            tp_price=tp,
            deviation_pct=deviation,
            rationale=(
                f"Vela elefante {direction}: cuerpo {ratio:.0%} del rango, "
                f"volumen {vol_ratio:.1f}x promedio. "
                f"Entry ${entry:.4f}, Stop ${stop:.4f}, TP ${tp:.4f}"
            ),
        )

    def detect_ignored_bar(
        self,
        symbol: str,
        candles: list,
        trend_state: str = "BULLISH",
    ) -> SignalCandidate | None:
        """Detecta patrón de barra ignorada (Oliver Vélez).

        Patrón alcista: GREEN-RED-GREEN (la roja es "ignorada")
        Patrón bajista: RED-GREEN-RED (la verde es "ignorada")

        La barra del medio es "ignorada" por el mercado — el movimiento
        continúa en la dirección original.

        Entry: ruptura del extremo de la 3ra barra.
        Stop: extremo opuesto de la barra ignorada.
        """
        if len(candles) < 4:
            return None

        bar1, bar2, bar3 = candles[-3], candles[-2], candles[-1]

        b1_bull = _is_bullish(bar1)
        b2_bull = _is_bullish(bar2)
        b3_bull = _is_bullish(bar3)

        # Patrón alcista: GREEN-RED-GREEN
        if b1_bull and not b2_bull and b3_bull:
            if trend_state == "BEARISH":
                return None  # Solo a favor de tendencia

            direction = "BUY"
            entry = bar3[2]          # Máximo de la 3ra barra
            stop = bar2[3]           # Mínimo de la barra ignorada (roja)
            risk = entry - stop
            if risk <= 0:
                return None
            tp = entry + risk * 2.5

        # Patrón bajista: RED-GREEN-RED
        elif not b1_bull and b2_bull and not b3_bull:
            if trend_state == "BULLISH":
                return None

            direction = "SELL"
            entry = bar3[3]          # Mínimo de la 3ra barra
            stop = bar2[2]           # Máximo de la barra ignorada (verde)
            risk = stop - entry
            if risk <= 0:
                return None
            tp = entry - risk * 2.5
        else:
            return None

        # Confidence: mayor si la barra ignorada es pequeña vs las otras
        ignored_range = bar2[2] - bar2[3]
        avg_range = ((bar1[2] - bar1[3]) + (bar3[2] - bar3[3])) / 2
        if avg_range > 0:
            size_ratio = ignored_range / avg_range
            # Barra ignorada más pequeña = mayor confianza
            confidence = min(0.45 + max(0, 1 - size_ratio) * 0.30, 0.85)
        else:
            confidence = 0.50

        deviation = abs(entry - bar3[4]) / bar3[4] * 100 if bar3[4] > 0 else 0

        return SignalCandidate(
            symbol=symbol,
            direction=direction,
            pattern_name="ignored_bar",
            confidence=confidence,
            entry_price=entry,
            stop_price=stop,
            tp_price=tp,
            deviation_pct=deviation,
            rationale=(
                f"Barra ignorada {direction}: patrón "
                f"{'GREEN-RED-GREEN' if direction == 'BUY' else 'RED-GREEN-RED'}. "
                f"Entry ${entry:.4f}, Stop ${stop:.4f}, TP ${tp:.4f}"
            ),
        )

    def detect_narrow_range_bars(
        self,
        symbol: str,
        candles: list,
        trend_state: str = "BULLISH",
    ) -> SignalCandidate | None:
        """Detecta barras de rango estrecho (NRB) — consolidación antes de explosión.

        2+ NRBs consecutivas = compresión de precio → movimiento explosivo.
        Rango de cada NRB < 50% del promedio de las últimas 10 velas.
        Dirección determinada por la tendencia (20/200 SMA).
        """
        if len(candles) < 12:
            return None

        # Calcular rango promedio de las últimas 10 velas (excluyendo las 2 últimas)
        lookback = candles[-12:-2]
        ranges = [c[2] - c[3] for c in lookback]
        avg_range = sum(ranges) / len(ranges) if ranges else 0
        if avg_range <= 0:
            return None

        threshold = avg_range * 0.50

        # Verificar si las últimas 2 velas son NRBs
        last_two = candles[-2:]
        nr_count = sum(1 for c in last_two if (c[2] - c[3]) < threshold)

        if nr_count < 2:
            return None

        # Dirección basada en tendencia
        current_price = candles[-1][4]
        if trend_state in ("BULLISH", "NARROW"):
            direction = "BUY"
            # Entry: ruptura del máximo de la consolidación
            consolidation_high = max(c[2] for c in last_two)
            consolidation_low = min(c[3] for c in last_two)
            entry = consolidation_high
            stop = consolidation_low
            risk = entry - stop
            if risk <= 0:
                return None
            tp = entry + risk * 2.5
        elif trend_state == "BEARISH":
            direction = "SELL"
            consolidation_high = max(c[2] for c in last_two)
            consolidation_low = min(c[3] for c in last_two)
            entry = consolidation_low
            stop = consolidation_high
            risk = stop - entry
            if risk <= 0:
                return None
            tp = entry - risk * 2.5
        else:
            return None  # MIXED — no operar

        # Confidence: más NRBs consecutivas = mayor compresión = mayor confianza
        confidence = min(0.45 + nr_count * 0.10, 0.80)
        deviation = abs(entry - current_price) / current_price * 100 if current_price > 0 else 0

        return SignalCandidate(
            symbol=symbol,
            direction=direction,
            pattern_name="narrow_range_bars",
            confidence=confidence,
            entry_price=entry,
            stop_price=stop,
            tp_price=tp,
            deviation_pct=deviation,
            rationale=(
                f"NRB consolidación ({nr_count} barras estrechas): "
                f"rango promedio ${avg_range:.4f}, NRBs < ${threshold:.4f}. "
                f"Breakout {direction} esperado. "
                f"Entry ${entry:.4f}, Stop ${stop:.4f}, TP ${tp:.4f}"
            ),
        )

    def detect_red_bar_reversal(
        self,
        symbol: str,
        candles: list,
        trend_state: str = "BULLISH",
    ) -> SignalCandidate | None:
        """Detecta Red Bar Reversal (Oliver Vélez).

        Tras una caída: barra roja con mecha inferior larga (>50% del rango)
        y cierre cerca del máximo. Indica rechazo del precio bajo.

        Solo alcista (BUY) — es un patrón de reversión alcista.
        Funciona mejor en tendencia alcista (pullback) o NARROW.
        """
        if len(candles) < 5:
            return None

        if trend_state == "BEARISH":
            return None  # Solo en contexto alcista o neutral

        last = candles[-1]
        o, h, l, c = last[1], last[2], last[3], last[4]
        rng = h - l
        if rng <= 0:
            return None

        # Debe ser una vela roja (bajista)
        if not _is_bearish(last):
            return None

        # Mecha inferior larga: > 50% del rango total
        lower_wick = min(o, c) - l
        lower_wick_ratio = lower_wick / rng

        if lower_wick_ratio < 0.50:
            return None

        # Cierre cerca del máximo: en el tercio superior
        close_position = (c - l) / rng
        if close_position < 0.60:
            return None

        # Verificar que hubo caída previa (al menos 2 velas bajistas antes)
        prior_bearish = sum(1 for c_bar in candles[-4:-1] if _is_bearish(c_bar))
        if prior_bearish < 1:
            return None

        direction = "BUY"
        entry = h  # Ruptura del máximo
        stop = l   # Mínimo de la vela de reversión
        risk = entry - stop
        if risk <= 0:
            return None
        tp = entry + risk * 2

        confidence = min(0.45 + lower_wick_ratio * 0.25 + close_position * 0.15, 0.85)
        deviation = abs(entry - c) / c * 100 if c > 0 else 0

        return SignalCandidate(
            symbol=symbol,
            direction=direction,
            pattern_name="red_bar_reversal",
            confidence=confidence,
            entry_price=entry,
            stop_price=stop,
            tp_price=tp,
            deviation_pct=deviation,
            rationale=(
                f"Red Bar Reversal: mecha inferior {lower_wick_ratio:.0%} del rango, "
                f"cierre en posición {close_position:.0%}. "
                f"Rechazo de precio bajo tras {prior_bearish} velas bajistas. "
                f"Entry ${entry:.4f}, Stop ${stop:.4f}, TP ${tp:.4f}"
            ),
        )

    def detect_all(
        self,
        symbol: str,
        candles: list,
        trend_state: str = "BULLISH",
    ) -> list[SignalCandidate]:
        """Ejecuta todos los detectores y retorna todas las señales encontradas."""
        candidates = []

        result = self.detect_elephant_bar(symbol, candles, trend_state)
        if result:
            candidates.append(result)

        result = self.detect_ignored_bar(symbol, candles, trend_state)
        if result:
            candidates.append(result)

        result = self.detect_narrow_range_bars(symbol, candles, trend_state)
        if result:
            candidates.append(result)

        result = self.detect_red_bar_reversal(symbol, candles, trend_state)
        if result:
            candidates.append(result)

        return candidates
