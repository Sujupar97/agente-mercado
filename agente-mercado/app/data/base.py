"""Interfaz abstracta para proveedores de datos externos."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExternalDataResult:
    """Resultado de una consulta de datos externos."""

    provider: str  # "coingecko" | "etherscan" | "gnews" | "reddit" | etc.
    symbol: str
    data: dict = field(default_factory=dict)
    error: str | None = None


class DataProvider(ABC):
    """Interfaz para proveedores de datos externos."""

    @abstractmethod
    async def fetch(self, symbol: str) -> ExternalDataResult:
        """Obtiene datos para un símbolo/token."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Libera recursos."""
        ...
