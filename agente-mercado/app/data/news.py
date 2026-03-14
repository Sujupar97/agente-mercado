"""Noticias cripto via GNews y NewsAPI."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.data.base import DataProvider, ExternalDataResult

log = logging.getLogger(__name__)


class GNewsProvider(DataProvider):
    """Noticias via GNews API (100 req/día gratis)."""

    BASE_URL = "https://gnews.io/api/v4"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)

    async def fetch(self, symbol: str) -> ExternalDataResult:
        if not settings.gnews_api_key:
            return ExternalDataResult(provider="gnews", symbol=symbol, error="No API key")

        base = symbol.split("/")[0]
        try:
            resp = await self._client.get(
                f"{self.BASE_URL}/search",
                params={
                    "q": f"{base} crypto",
                    "lang": "en",
                    "max": 5,
                    "sortby": "publishedAt",
                    "token": settings.gnews_api_key,
                },
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            headlines = [
                {
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "published_at": a.get("publishedAt", ""),
                    "source": a.get("source", {}).get("name", ""),
                }
                for a in articles[:5]
            ]
            return ExternalDataResult(
                provider="gnews",
                symbol=symbol,
                data={"articles_count": len(headlines), "headlines": headlines},
            )
        except Exception as e:
            return ExternalDataResult(provider="gnews", symbol=symbol, error=str(e))

    async def close(self) -> None:
        await self._client.aclose()


class NewsAPIProvider(DataProvider):
    """Noticias via NewsAPI.org (100 req/día gratis, 24h delay)."""

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)

    async def fetch(self, symbol: str) -> ExternalDataResult:
        if not settings.newsapi_key:
            return ExternalDataResult(provider="newsapi", symbol=symbol, error="No API key")

        base = symbol.split("/")[0]
        try:
            resp = await self._client.get(
                f"{self.BASE_URL}/everything",
                params={
                    "q": f"{base} cryptocurrency",
                    "language": "en",
                    "pageSize": 5,
                    "sortBy": "publishedAt",
                    "apiKey": settings.newsapi_key,
                },
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            headlines = [
                {
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "published_at": a.get("publishedAt", ""),
                    "source": a.get("source", {}).get("name", ""),
                }
                for a in articles[:5]
            ]
            return ExternalDataResult(
                provider="newsapi",
                symbol=symbol,
                data={"articles_count": len(headlines), "headlines": headlines},
            )
        except Exception as e:
            return ExternalDataResult(provider="newsapi", symbol=symbol, error=str(e))

    async def close(self) -> None:
        await self._client.aclose()
