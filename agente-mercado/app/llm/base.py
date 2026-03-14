"""Interfaz abstracta para clientes LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.data.router import EnrichedMarket


@dataclass
class ProbabilityEstimate:
    """Estimación del LLM para un par/mercado."""

    symbol: str
    direction: str  # "BUY" | "SELL" | "HOLD"
    confidence: float  # 0.0 - 1.0
    deviation_pct: float  # (fair - current) / current como decimal
    take_profit_pct: float  # e.g. 0.04 = 4%
    stop_loss_pct: float  # e.g. 0.02 = 2%
    rationale: str  # Explicación breve
    data_sources: list[str] = field(default_factory=list)


class LLMClient(ABC):
    """Interfaz genérica para cualquier modelo LLM."""

    @abstractmethod
    async def estimate_fair_values(
        self,
        markets: list[EnrichedMarket],
        model_override: str | None = None,
        performance_context: str = "",
        system_prompt_override: str = "",
        user_prompt_override: str = "",
    ) -> list[ProbabilityEstimate]:
        """Estima valor justo para un batch de mercados."""
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
