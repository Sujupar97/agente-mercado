"""Interfaz abstracta para proveedores de mercado."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MarketTicker:
    """Datos de un par/mercado escaneado."""

    id: str  # e.g. "binance:BTC/USDT"
    source: str  # "binance" | "bybit"
    symbol: str  # "BTC/USDT"
    price: float
    bid: float
    ask: float
    volume_24h: float  # en USD
    change_24h_pct: float = 0.0
    market_cap: float | None = None
    extra: dict = field(default_factory=dict)

    @property
    def bid_ask_spread_pct(self) -> float:
        if self.bid <= 0:
            return 999.0
        return ((self.ask - self.bid) / self.bid) * 100


class MarketProvider(ABC):
    """Interfaz para cualquier fuente de datos de mercado."""

    @abstractmethod
    async def fetch_tickers(self, limit: int = 500) -> list[MarketTicker]:
        """Obtiene tickers de los pares más activos."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Libera recursos (conexiones, etc.)."""
        ...
