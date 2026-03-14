"""Datos on-chain: CoinGecko + Etherscan + DeFi Llama."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.data.base import DataProvider, ExternalDataResult

log = logging.getLogger(__name__)


class CoinGeckoProvider(DataProvider):
    """Precios, market cap, volumen via CoinGecko Demo API."""

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self) -> None:
        headers = {}
        if settings.coingecko_api_key:
            headers["x-cg-demo-key"] = settings.coingecko_api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL, headers=headers, timeout=15.0
        )
        # Cache de mapeo symbol → coingecko_id
        self._id_map: dict[str, str] = {}

    async def _ensure_id_map(self) -> None:
        """Carga el mapeo de símbolos a IDs de CoinGecko (una vez)."""
        if self._id_map:
            return
        try:
            resp = await self._client.get("/coins/list")
            resp.raise_for_status()
            for coin in resp.json():
                sym = coin.get("symbol", "").upper()
                self._id_map[sym] = coin["id"]
        except Exception:
            log.exception("Error cargando lista de monedas de CoinGecko")

    async def fetch(self, symbol: str) -> ExternalDataResult:
        """Obtiene datos de mercado para un símbolo (e.g. 'BTC')."""
        await self._ensure_id_map()
        base = symbol.split("/")[0].upper()
        coin_id = self._id_map.get(base)
        if not coin_id:
            return ExternalDataResult(provider="coingecko", symbol=symbol, error="ID no encontrado")

        try:
            resp = await self._client.get(
                f"/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "community_data": "true",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            market_data = data.get("market_data", {})
            return ExternalDataResult(
                provider="coingecko",
                symbol=symbol,
                data={
                    "market_cap_usd": market_data.get("market_cap", {}).get("usd"),
                    "total_volume_usd": market_data.get("total_volume", {}).get("usd"),
                    "price_change_7d_pct": market_data.get("price_change_percentage_7d"),
                    "price_change_30d_pct": market_data.get("price_change_percentage_30d"),
                    "ath_usd": market_data.get("ath", {}).get("usd"),
                    "ath_change_pct": market_data.get("ath_change_percentage", {}).get("usd"),
                    "circulating_supply": market_data.get("circulating_supply"),
                    "total_supply": market_data.get("total_supply"),
                    "reddit_subscribers": data.get("community_data", {}).get(
                        "reddit_subscribers"
                    ),
                    "sentiment_up_pct": data.get("sentiment_votes_up_percentage"),
                    "sentiment_down_pct": data.get("sentiment_votes_down_percentage"),
                },
            )
        except Exception as e:
            return ExternalDataResult(
                provider="coingecko", symbol=symbol, error=str(e)
            )

    async def close(self) -> None:
        await self._client.aclose()


class EtherscanProvider(DataProvider):
    """Datos de Ethereum: gas, transacciones de whales."""

    BASE_URL = "https://api.etherscan.io/api"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)

    async def fetch(self, symbol: str) -> ExternalDataResult:
        """Obtiene gas price y stats generales de Ethereum."""
        if not settings.etherscan_api_key:
            return ExternalDataResult(
                provider="etherscan", symbol=symbol, error="No API key"
            )
        try:
            # Gas price actual
            gas_resp = await self._client.get(
                self.BASE_URL,
                params={
                    "module": "gastracker",
                    "action": "gasoracle",
                    "apikey": settings.etherscan_api_key,
                },
            )
            gas_data = gas_resp.json().get("result", {})

            # ETH supply
            supply_resp = await self._client.get(
                self.BASE_URL,
                params={
                    "module": "stats",
                    "action": "ethsupply",
                    "apikey": settings.etherscan_api_key,
                },
            )
            supply = supply_resp.json().get("result", "0")

            return ExternalDataResult(
                provider="etherscan",
                symbol=symbol,
                data={
                    "gas_low": gas_data.get("SafeGasPrice"),
                    "gas_average": gas_data.get("ProposeGasPrice"),
                    "gas_high": gas_data.get("FastGasPrice"),
                    "eth_supply_wei": supply,
                },
            )
        except Exception as e:
            return ExternalDataResult(provider="etherscan", symbol=symbol, error=str(e))

    async def close(self) -> None:
        await self._client.aclose()


class DefiLlamaProvider(DataProvider):
    """TVL de protocolos DeFi via DeFi Llama (gratis, sin auth)."""

    BASE_URL = "https://api.llama.fi"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=self.BASE_URL, timeout=15.0)
        self._protocols: dict[str, dict] | None = None

    async def _ensure_protocols(self) -> None:
        if self._protocols is not None:
            return
        try:
            resp = await self._client.get("/protocols")
            resp.raise_for_status()
            self._protocols = {}
            for p in resp.json():
                sym = (p.get("symbol") or "").upper()
                if sym:
                    self._protocols[sym] = {
                        "name": p.get("name"),
                        "tvl": p.get("tvl"),
                        "chain": p.get("chain"),
                        "category": p.get("category"),
                        "change_1d": p.get("change_1d"),
                        "change_7d": p.get("change_7d"),
                    }
        except Exception:
            log.exception("Error cargando protocolos de DeFi Llama")
            self._protocols = {}

    async def fetch(self, symbol: str) -> ExternalDataResult:
        await self._ensure_protocols()
        base = symbol.split("/")[0].upper()
        protocol = (self._protocols or {}).get(base)
        if not protocol:
            return ExternalDataResult(
                provider="defillama", symbol=symbol, data={"tvl": None}
            )
        return ExternalDataResult(
            provider="defillama", symbol=symbol, data=protocol
        )

    async def close(self) -> None:
        await self._client.aclose()
