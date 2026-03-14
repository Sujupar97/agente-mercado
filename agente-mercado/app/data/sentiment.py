"""Sentimiento social via Reddit API (60 req/min, OAuth)."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.data.base import DataProvider, ExternalDataResult

log = logging.getLogger(__name__)


class RedditSentimentProvider(DataProvider):
    """Analiza sentimiento de r/cryptocurrency y r/bitcoin."""

    AUTH_URL = "https://www.reddit.com/api/v1/access_token"
    BASE_URL = "https://oauth.reddit.com"
    USER_AGENT = "AgenteMercado/0.1 by agente-mercado-bot"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._token: str | None = None

    async def _ensure_token(self) -> bool:
        if self._token:
            return True
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            return False
        try:
            resp = await self._client.post(
                self.AUTH_URL,
                auth=(settings.reddit_client_id, settings.reddit_client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self.USER_AGENT},
            )
            resp.raise_for_status()
            self._token = resp.json().get("access_token")
            return bool(self._token)
        except Exception:
            log.exception("Error autenticando con Reddit")
            return False

    async def fetch(self, symbol: str) -> ExternalDataResult:
        if not await self._ensure_token():
            return ExternalDataResult(
                provider="reddit", symbol=symbol, error="No auth"
            )

        base = symbol.split("/")[0].lower()
        subreddits = ["cryptocurrency"]
        if base == "btc":
            subreddits.append("bitcoin")
        elif base == "eth":
            subreddits.append("ethereum")

        all_posts: list[dict] = []
        for sub in subreddits:
            try:
                resp = await self._client.get(
                    f"{self.BASE_URL}/r/{sub}/search",
                    params={
                        "q": base,
                        "sort": "new",
                        "t": "day",  # últimas 24h
                        "limit": 10,
                        "restrict_sr": "true",
                    },
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "User-Agent": self.USER_AGENT,
                    },
                )
                resp.raise_for_status()
                posts = resp.json().get("data", {}).get("children", [])
                for post in posts:
                    d = post.get("data", {})
                    all_posts.append(
                        {
                            "title": d.get("title", ""),
                            "score": d.get("score", 0),
                            "num_comments": d.get("num_comments", 0),
                            "upvote_ratio": d.get("upvote_ratio", 0),
                            "subreddit": sub,
                        }
                    )
            except Exception:
                log.exception("Error buscando en r/%s", sub)

        # Calcular sentimiento simple
        if all_posts:
            avg_score = sum(p["score"] for p in all_posts) / len(all_posts)
            avg_upvote = sum(p["upvote_ratio"] for p in all_posts) / len(all_posts)
            total_comments = sum(p["num_comments"] for p in all_posts)
        else:
            avg_score = 0
            avg_upvote = 0.5
            total_comments = 0

        return ExternalDataResult(
            provider="reddit",
            symbol=symbol,
            data={
                "posts_found": len(all_posts),
                "avg_score": round(avg_score, 1),
                "avg_upvote_ratio": round(avg_upvote, 3),
                "total_comments": total_comments,
                "top_titles": [p["title"] for p in all_posts[:3]],
                "sentiment_score": round(avg_upvote * 2 - 1, 3),  # -1 a +1
            },
        )

    async def close(self) -> None:
        await self._client.aclose()
