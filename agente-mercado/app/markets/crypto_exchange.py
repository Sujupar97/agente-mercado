"""Proveedor de mercados cripto via ccxt (Binance / Bybit)."""

from __future__ import annotations

import logging

import ccxt.async_support as ccxt

from app.config import settings
from app.markets.base import MarketProvider, MarketTicker

log = logging.getLogger(__name__)


class CryptoExchangeProvider(MarketProvider):
    """Obtiene tickers de Binance y/o Bybit usando ccxt async."""

    def __init__(self) -> None:
        self._exchanges: list[ccxt.Exchange] = []
        self._init_exchanges()

    def _init_exchanges(self) -> None:
        # Binance
        if settings.binance_api_key:
            binance_config = {
                "apiKey": settings.binance_api_key,
                "secret": settings.binance_api_secret,
                "enableRateLimit": True,
            }
            if settings.binance_testnet:
                binance_config["sandbox"] = True
            self._exchanges.append(("binance", ccxt.binance(binance_config)))
            log.info(
                "Binance configurado (testnet=%s)", settings.binance_testnet
            )
        else:
            # Sin API key: solo lectura de mercado (público)
            self._exchanges.append(("binance", ccxt.binance({"enableRateLimit": True})))
            log.info("Binance configurado (solo lectura, sin API key)")

        # Bybit
        if settings.bybit_api_key:
            self._exchanges.append(
                (
                    "bybit",
                    ccxt.bybit(
                        {
                            "apiKey": settings.bybit_api_key,
                            "secret": settings.bybit_api_secret,
                            "enableRateLimit": True,
                        }
                    ),
                )
            )
            log.info("Bybit configurado")

    async def fetch_tickers(self, limit: int = 500) -> list[MarketTicker]:
        """Obtiene los top `limit` pares USDT por volumen de todos los exchanges."""
        all_tickers: list[MarketTicker] = []

        for name, exchange in self._exchanges:
            try:
                raw_tickers = await exchange.fetch_tickers()
                usdt_tickers = self._filter_and_convert(name, raw_tickers, limit)
                all_tickers.extend(usdt_tickers)
                log.info("%s: %d pares obtenidos", name, len(usdt_tickers))
            except Exception:
                log.exception("Error obteniendo tickers de %s", name)

        # Ordenar por volumen y limitar
        all_tickers.sort(key=lambda t: t.volume_24h, reverse=True)
        return all_tickers[:limit]

    def _filter_and_convert(
        self, source: str, raw: dict, limit: int
    ) -> list[MarketTicker]:
        """Filtra pares /USDT y convierte a MarketTicker."""
        tickers = []
        for symbol, data in raw.items():
            # Solo pares contra USDT
            if not symbol.endswith("/USDT"):
                continue

            last_price = data.get("last") or 0
            bid = data.get("bid") or 0
            ask = data.get("ask") or 0
            # quoteVolume = volumen en USDT
            volume_usd = data.get("quoteVolume") or 0
            change_pct = data.get("percentage") or 0

            if last_price <= 0 or volume_usd < settings.min_volume_usd:
                continue

            tickers.append(
                MarketTicker(
                    id=f"{source}:{symbol}",
                    source=source,
                    symbol=symbol,
                    price=last_price,
                    bid=bid,
                    ask=ask,
                    volume_24h=volume_usd,
                    change_24h_pct=change_pct,
                )
            )

        tickers.sort(key=lambda t: t.volume_24h, reverse=True)
        return tickers[:limit]

    async def close(self) -> None:
        for name, exchange in self._exchanges:
            try:
                await exchange.close()
            except Exception:
                log.exception("Error cerrando %s", name)
