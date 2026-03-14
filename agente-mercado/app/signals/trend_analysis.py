"""Análisis de tendencia con sistema 20/200 SMA de Oliver Vélez.

TrendState determina la dirección permitida para operar:
- BULLISH: precio > SMA20 > SMA200 → solo BUY
- BEARISH: precio < SMA20 < SMA200 → solo SELL
- NARROW: SMAs convergentes (<1% diferencia) → explosión inminente, ambas direcciones
- MIXED: precio entre SMAs → no operar (o con precaución)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class TrendState:
    """Estado de tendencia para un símbolo."""

    state: str           # "BULLISH" | "BEARISH" | "NARROW" | "MIXED"
    sma20: float
    sma200: float
    price: float
    sma_distance_pct: float   # abs(sma20 - sma200) / sma200 * 100
    price_vs_sma20_pct: float  # (price - sma20) / sma20 * 100


@dataclass
class MultiTFAlignment:
    """Alineación de tendencia en múltiples timeframes."""

    primary_trend: str     # Tendencia del TF mayor (1h)
    aligned: bool          # True si todos los TFs coinciden
    tf_states: dict[str, str]  # {"5m": "BULLISH", "15m": "BULLISH", "1h": "BULLISH"}
    strength: float        # 0-1, mayor = más alineado


class TrendAnalyzer:
    """Sistema 20/200 SMA de Oliver Vélez para determinar tendencia."""

    @staticmethod
    def calculate_sma(closes: list[float], period: int) -> float:
        """Calcula SMA para un período dado."""
        if len(closes) < period:
            return sum(closes) / max(len(closes), 1)
        return sum(closes[-period:]) / period

    def get_trend_state(self, candles_1h: list) -> TrendState:
        """Determina el estado de tendencia con 20/200 SMA.

        Args:
            candles_1h: Velas de 1h con al menos 200+ períodos.
                        Formato: [timestamp, O, H, L, C, V]

        Returns:
            TrendState con la clasificación de tendencia.
        """
        if len(candles_1h) < 20:
            return TrendState(
                state="MIXED", sma20=0, sma200=0, price=0,
                sma_distance_pct=0, price_vs_sma20_pct=0,
            )

        closes = [c[4] for c in candles_1h]
        price = closes[-1]
        sma20 = self.calculate_sma(closes, 20)

        # Si no hay suficientes datos para SMA200, usar lo que hay
        if len(closes) >= 200:
            sma200 = self.calculate_sma(closes, 200)
        elif len(closes) >= 50:
            # Usar SMA50 como proxy cuando no hay 200 períodos
            sma200 = self.calculate_sma(closes, len(closes))
        else:
            sma200 = sma20  # Sin datos suficientes, asumir NARROW

        # Distancia entre SMAs
        sma_distance_pct = abs(sma20 - sma200) / sma200 * 100 if sma200 > 0 else 0
        price_vs_sma20 = (price - sma20) / sma20 * 100 if sma20 > 0 else 0

        # Clasificación según Oliver Vélez
        if sma_distance_pct < 1.0:
            # NARROW STATE: SMAs muy cerca → compresión, explosión inminente
            state = "NARROW"
        elif price > sma20 > sma200:
            # BULLISH: precio sobre ambas SMAs, SMA20 sobre SMA200
            state = "BULLISH"
        elif price < sma20 < sma200:
            # BEARISH: precio bajo ambas SMAs, SMA20 bajo SMA200
            state = "BEARISH"
        else:
            # MIXED: precio entre SMAs o SMAs cruzándose
            state = "MIXED"

        return TrendState(
            state=state,
            sma20=sma20,
            sma200=sma200,
            price=price,
            sma_distance_pct=sma_distance_pct,
            price_vs_sma20_pct=price_vs_sma20,
        )

    def get_trend_for_timeframe(self, candles: list) -> str:
        """Versión simplificada: retorna solo el estado como string."""
        if len(candles) < 20:
            return "MIXED"

        closes = [c[4] for c in candles]
        price = closes[-1]
        sma20 = self.calculate_sma(closes, 20)

        if len(closes) >= 50:
            sma_long = self.calculate_sma(closes, min(len(closes), 200))
        else:
            return "MIXED"

        sma_distance_pct = abs(sma20 - sma_long) / sma_long * 100 if sma_long > 0 else 0

        if sma_distance_pct < 1.0:
            return "NARROW"
        elif price > sma20 > sma_long:
            return "BULLISH"
        elif price < sma20 < sma_long:
            return "BEARISH"
        return "MIXED"

    def get_multi_tf_alignment(
        self,
        candles_5m: list | None = None,
        candles_15m: list | None = None,
        candles_1h: list | None = None,
    ) -> MultiTFAlignment:
        """Verifica consistencia de tendencia en múltiples timeframes.

        Oliver Vélez opera A FAVOR del timeframe mayor.
        La alineación multi-TF aumenta la confianza de las señales.
        """
        tf_states: dict[str, str] = {}

        if candles_1h:
            trend_1h = self.get_trend_state(candles_1h)
            tf_states["1h"] = trend_1h.state
        else:
            tf_states["1h"] = "MIXED"

        if candles_15m:
            tf_states["15m"] = self.get_trend_for_timeframe(candles_15m)

        if candles_5m:
            tf_states["5m"] = self.get_trend_for_timeframe(candles_5m)

        # Tendencia primaria = timeframe más grande
        primary = tf_states.get("1h", "MIXED")

        # Calcular alineación
        directional_states = [s for s in tf_states.values() if s in ("BULLISH", "BEARISH")]

        if not directional_states:
            aligned = False
            strength = 0.3
        else:
            all_same = len(set(directional_states)) == 1
            aligned = all_same and primary in ("BULLISH", "BEARISH")

            # Strength: qué fracción de TFs coinciden con el primario
            matching = sum(1 for s in tf_states.values() if s == primary)
            strength = matching / len(tf_states)

        return MultiTFAlignment(
            primary_trend=primary,
            aligned=aligned,
            tf_states=tf_states,
            strength=strength,
        )

    def get_sma_pullback_signal(
        self,
        symbol: str,
        candles_1h: list,
        candles_15m: list | None = None,
    ) -> dict | None:
        """Detecta oportunidad de pullback a SMA20 en tendencia establecida.

        Estrategia oliver_sma: Precio en tendencia clara, retrocede a SMA20,
        y rebota. Entry cuando el precio toca/cruza SMA20 y rebota.
        """
        trend = self.get_trend_state(candles_1h)

        if trend.state not in ("BULLISH", "BEARISH"):
            return None

        # El precio debe estar cerca de SMA20 (dentro del 1%)
        if abs(trend.price_vs_sma20_pct) > 1.5:
            return None

        # Verificar rebote: las últimas 2-3 velas deben mostrar rechazo de SMA20
        if len(candles_1h) < 5:
            return None

        recent = candles_1h[-3:]

        if trend.state == "BULLISH":
            # Precio bajó hacia SMA20 y está rebotando
            touched_sma = any(c[3] <= trend.sma20 * 1.005 for c in recent)  # Low tocó SMA20
            bouncing = candles_1h[-1][4] > candles_1h[-2][4]  # Último cierre > anterior

            if not (touched_sma and bouncing):
                return None

            direction = "BUY"
            entry = candles_1h[-1][4]  # Cierre actual
            stop = trend.sma20 * 0.99  # Bajo SMA20 (1% debajo)
            risk = entry - stop
            if risk <= 0:
                return None
            tp = entry + risk * 2.5

        else:  # BEARISH
            touched_sma = any(c[2] >= trend.sma20 * 0.995 for c in recent)
            bouncing = candles_1h[-1][4] < candles_1h[-2][4]

            if not (touched_sma and bouncing):
                return None

            direction = "SELL"
            entry = candles_1h[-1][4]
            stop = trend.sma20 * 1.01
            risk = stop - entry
            if risk <= 0:
                return None
            tp = entry - risk * 2.5

        confidence = 0.55 + trend.sma_distance_pct * 0.02  # Más separadas = más fuerte
        confidence = min(confidence, 0.85)

        return {
            "symbol": symbol,
            "direction": direction,
            "pattern_name": "sma_pullback",
            "confidence": confidence,
            "entry_price": entry,
            "stop_price": stop,
            "tp_price": tp,
            "trend_state": trend.state,
            "sma20": trend.sma20,
            "sma200": trend.sma200,
            "rationale": (
                f"Pullback a SMA20 en tendencia {trend.state}: "
                f"precio ${entry:.4f}, SMA20 ${trend.sma20:.4f}, "
                f"SMA200 ${trend.sma200:.4f}. "
                f"Distancia SMAs: {trend.sma_distance_pct:.1f}%."
            ),
        }
