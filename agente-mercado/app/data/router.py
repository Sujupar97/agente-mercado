"""Enrutador de datos — para cada par cripto, consulta los proveedores relevantes."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from app.config import settings
from app.data.base import ExternalDataResult
from app.data.crypto_onchain import CoinGeckoProvider, DefiLlamaProvider, EtherscanProvider
from app.data.news import GNewsProvider, NewsAPIProvider
from app.data.sentiment import RedditSentimentProvider
from app.markets.base import MarketTicker

log = logging.getLogger(__name__)


@dataclass
class EnrichedMarket:
    """Mercado con datos externos adjuntos."""

    ticker: MarketTicker
    external_data: list[ExternalDataResult] = field(default_factory=list)

    @property
    def data_summary(self) -> dict:
        """Resumen plano de todos los datos externos para el LLM."""
        summary: dict = {
            "symbol": self.ticker.symbol,
            "price": self.ticker.price,
            "volume_24h": self.ticker.volume_24h,
            "change_24h_pct": self.ticker.change_24h_pct,
        }
        for result in self.external_data:
            if result.error:
                continue
            for k, v in result.data.items():
                summary[f"{result.provider}_{k}"] = v
        return summary


class DataRouter:
    """Enruta cada par a sus proveedores de datos relevantes con cache Redis."""

    # TTL de cache por proveedor (en segundos)
    CACHE_TTL = {
        "coingecko": 300,  # 5 min
        "etherscan": 600,  # 10 min
        "defillama": 900,  # 15 min
        "gnews": 1800,  # 30 min
        "newsapi": 1800,  # 30 min
        "reddit": 900,  # 15 min
    }

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._coingecko = CoinGeckoProvider()
        self._etherscan = EtherscanProvider()
        self._defillama = DefiLlamaProvider()
        self._gnews = GNewsProvider()
        self._newsapi = NewsAPIProvider()
        self._reddit = RedditSentimentProvider()

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def _get_cached(self, provider: str, symbol: str) -> ExternalDataResult | None:
        """Busca en cache Redis."""
        try:
            r = await self._get_redis()
            key = f"data:{provider}:{symbol}"
            cached = await r.get(key)
            if cached:
                data = json.loads(cached)
                return ExternalDataResult(
                    provider=provider, symbol=symbol, data=data
                )
        except Exception:
            pass
        return None

    async def _set_cache(self, result: ExternalDataResult) -> None:
        """Guarda resultado en cache Redis."""
        if result.error:
            return
        try:
            r = await self._get_redis()
            key = f"data:{result.provider}:{result.symbol}"
            ttl = self.CACHE_TTL.get(result.provider, 300)
            await r.set(key, json.dumps(result.data), ex=ttl)
        except Exception:
            pass

    async def _fetch_with_cache(
        self, provider_name: str, provider, symbol: str
    ) -> ExternalDataResult:
        """Fetch con cache Redis."""
        cached = await self._get_cached(provider_name, symbol)
        if cached:
            return cached
        result = await provider.fetch(symbol)
        await self._set_cache(result)
        return result

    async def enrich(self, tickers: list[MarketTicker]) -> list[EnrichedMarket]:
        """Enriquece una lista de tickers con datos externos (en paralelo)."""
        enriched = []

        # Procesar en batches de 10 para no saturar APIs
        for i in range(0, len(tickers), 10):
            batch = tickers[i : i + 10]
            tasks = [self._enrich_single(t) for t in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for t, r in zip(batch, results):
                if isinstance(r, Exception):
                    log.warning("Error enriqueciendo %s: %s", t.symbol, r)
                    enriched.append(EnrichedMarket(ticker=t))
                else:
                    enriched.append(r)

        return enriched

    async def _enrich_single(self, ticker: MarketTicker) -> EnrichedMarket:
        """Enriquece un solo ticker con todos los proveedores relevantes."""
        symbol = ticker.symbol
        tasks = [
            self._fetch_with_cache("coingecko", self._coingecko, symbol),
            self._fetch_with_cache("defillama", self._defillama, symbol),
        ]

        # Etherscan solo para tokens Ethereum-related
        base = symbol.split("/")[0].upper()
        if base in ("ETH", "UNI", "LINK", "AAVE", "MKR", "COMP", "SNX", "CRV", "LDO"):
            tasks.append(self._fetch_with_cache("etherscan", self._etherscan, symbol))

        # Noticias: solo para los top 50 por volumen (conservar rate limits)
        tasks.append(self._fetch_with_cache("gnews", self._gnews, symbol))

        # Reddit: solo para pares principales
        if base in ("BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "DOT", "MATIC", "LINK"):
            tasks.append(self._fetch_with_cache("reddit", self._reddit, symbol))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        external = []
        for r in results:
            if isinstance(r, ExternalDataResult):
                external.append(r)

        return EnrichedMarket(ticker=ticker, external_data=external)

    async def close(self) -> None:
        await self._coingecko.close()
        await self._etherscan.close()
        await self._defillama.close()
        await self._gnews.close()
        await self._newsapi.close()
        await self._reddit.close()
        if self._redis:
            await self._redis.aclose()
