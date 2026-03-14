"""OHLCV multi-timeframe data provider via CCXT (gratis, sin API key).

Expandido para soportar múltiples timeframes necesarios por las
estrategias de Oliver Vélez:
- 5m: detección de patrones (elephant bars, ignored bars)
- 15m: confirmación de patrones
- 1h: tendencia (20/200 SMA) — necesita 250 velas para SMA200
- 1d: contexto macro
"""

from __future__ import annotations

import logging

import ccxt.async_support as ccxt

log = logging.getLogger(__name__)

# Timeframes y cantidad de velas por estrategia
STRATEGY_TIMEFRAMES: dict[str, dict[str, int]] = {
    "oliver_elephant": {"5m": 100, "15m": 50, "1h": 250},
    "oliver_sma": {"15m": 50, "1h": 250},
    "oliver_ignored": {"5m": 100, "15m": 50, "1h": 250},
    "andres_valdez": {"15m": 50, "1h": 250, "1d": 30},
}

DEFAULT_TIMEFRAMES: dict[str, int] = {"1h": 250}


class OHLCVProvider:
    """Obtiene datos de velas (candlestick) de Binance para análisis técnico."""

    def __init__(self) -> None:
        self._exchange: ccxt.Exchange | None = None
        self._cache: dict[str, list] = {}

    async def _get_exchange(self) -> ccxt.Exchange:
        if self._exchange is None:
            self._exchange = ccxt.binance({"enableRateLimit": True})
        return self._exchange

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 50,
    ) -> list:
        """Obtiene velas OHLCV. Retorna lista de [timestamp, O, H, L, C, V]."""
        cache_key = f"{symbol}:{timeframe}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            exchange = await self._get_exchange()
            candles = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            self._cache[cache_key] = candles
            return candles
        except Exception:
            log.debug("Error obteniendo OHLCV para %s %s", symbol, timeframe)
            return []

    async def fetch_multi_timeframe(
        self, symbol: str, strategy_id: str,
    ) -> dict[str, list]:
        """Obtiene velas en todos los timeframes necesarios para una estrategia.

        Returns:
            {"5m": [[ts, O, H, L, C, V], ...], "15m": [...], "1h": [...]}
        """
        tf_config = STRATEGY_TIMEFRAMES.get(strategy_id, DEFAULT_TIMEFRAMES)
        result: dict[str, list] = {}

        for tf, limit in tf_config.items():
            candles = await self.fetch_ohlcv(symbol, tf, limit)
            if candles:
                result[tf] = candles

        return result

    async def get_technical_summary(self, symbol: str) -> dict:
        """Calcula indicadores clave — incluye SMA200 y trend state."""
        candles_1h = await self.fetch_ohlcv(symbol, "1h", 250)
        if len(candles_1h) < 14:
            return {}

        closes = [c[4] for c in candles_1h]
        highs = [c[2] for c in candles_1h]
        lows = [c[3] for c in candles_1h]
        volumes = [c[5] for c in candles_1h]
        current = closes[-1] if closes else 0

        sma20 = self._calc_sma(closes, 20)
        sma200 = self._calc_sma(closes, 200) if len(closes) >= 200 else self._calc_sma(closes, len(closes))
        rsi = self._calc_rsi(closes, 14)
        atr = self._calc_atr(highs, lows, closes, 14)

        # Tendencia de volumen
        recent_vol = sum(volumes[-6:]) / max(len(volumes[-6:]), 1)
        avg_vol = sum(volumes) / max(len(volumes), 1)
        vol_trend = "increasing" if recent_vol > avg_vol * 1.1 else (
            "decreasing" if recent_vol < avg_vol * 0.9 else "stable"
        )

        price_vs_sma20 = ((current - sma20) / sma20 * 100) if sma20 > 0 else 0
        price_vs_sma200 = ((current - sma200) / sma200 * 100) if sma200 > 0 else 0
        sma_distance = abs(sma20 - sma200) / sma200 * 100 if sma200 > 0 else 0

        # Trend state según Oliver Vélez
        if sma_distance < 1.0:
            trend_state = "NARROW"
        elif current > sma20 > sma200:
            trend_state = "BULLISH"
        elif current < sma20 < sma200:
            trend_state = "BEARISH"
        else:
            trend_state = "MIXED"

        return {
            "sma20_1h": round(sma20, 6),
            "sma200_1h": round(sma200, 6),
            "rsi14_1h": round(rsi, 1),
            "atr14_1h": round(atr, 6),
            "atr_pct": round(atr / current * 100, 2) if current > 0 else 0,
            "volume_trend": vol_trend,
            "price_vs_sma20_pct": round(price_vs_sma20, 2),
            "price_vs_sma200_pct": round(price_vs_sma200, 2),
            "sma_distance_pct": round(sma_distance, 2),
            "trend_state": trend_state,
        }

    @staticmethod
    def _calc_sma(closes: list[float], period: int) -> float:
        """Calcula SMA (Simple Moving Average)."""
        if not closes:
            return 0.0
        if len(closes) < period:
            return sum(closes) / len(closes)
        return sum(closes[-period:]) / period

    @staticmethod
    def _calc_rsi(closes: list[float], period: int = 14) -> float:
        """Calcula RSI (Relative Strength Index)."""
        if len(closes) < period + 1:
            return 50.0

        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calc_atr(
        highs: list[float], lows: list[float], closes: list[float], period: int = 14,
    ) -> float:
        """Calcula ATR (Average True Range)."""
        if len(highs) < period + 1:
            return 0.0

        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            true_ranges.append(tr)

        return sum(true_ranges[-period:]) / period

    @staticmethod
    def calculate_body_ratio(candle: list) -> float:
        """Calcula ratio cuerpo/rango de una vela."""
        o, h, l, c = candle[1], candle[2], candle[3], candle[4]
        rng = h - l
        if rng <= 0:
            return 0.0
        return abs(c - o) / rng

    @staticmethod
    def calculate_volume_ratio(candles: list, index: int = -1, lookback: int = 20) -> float:
        """Calcula ratio de volumen de una vela vs promedio."""
        if not candles or abs(index) > len(candles):
            return 1.0
        vol = candles[index][5]
        start = max(0, len(candles) + index - lookback)
        end = len(candles) + index
        avg_vols = [c[5] for c in candles[start:end]]
        avg = sum(avg_vols) / max(len(avg_vols), 1)
        return vol / avg if avg > 0 else 1.0

    @staticmethod
    def is_narrow_range(candle: list, candles: list, lookback: int = 10) -> bool:
        """Verifica si una vela tiene rango estrecho vs promedio."""
        rng = candle[2] - candle[3]
        recent = candles[-lookback:] if len(candles) >= lookback else candles
        avg_range = sum(c[2] - c[3] for c in recent) / max(len(recent), 1)
        return rng < avg_range * 0.50

    def clear_cache(self) -> None:
        """Limpia cache al inicio de cada ciclo."""
        self._cache.clear()

    async def close(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
