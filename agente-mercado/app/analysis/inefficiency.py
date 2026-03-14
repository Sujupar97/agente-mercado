"""Detección de ineficiencias — desviación precio vs valor justo."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings
from app.llm.base import ProbabilityEstimate

log = logging.getLogger(__name__)


@dataclass
class Opportunity:
    """Oportunidad de trading detectada."""

    signal: ProbabilityEstimate
    passes_threshold: bool
    passes_confidence: bool

    @property
    def is_valid(self) -> bool:
        return self.passes_threshold and self.passes_confidence


class InefficiencyDetector:
    """Detecta desviaciones significativas entre precio y valor justo."""

    def __init__(
        self,
        deviation_threshold: float | None = None,
        min_confidence: float | None = None,
    ) -> None:
        self._deviation_threshold = deviation_threshold or settings.deviation_threshold
        self._min_confidence = min_confidence or settings.min_confidence

    def detect(self, signals: list[ProbabilityEstimate]) -> list[Opportunity]:
        """Filtra señales que superan el umbral de desviación y confianza."""
        opportunities = []

        for signal in signals:
            passes_threshold = abs(signal.deviation_pct) >= self._deviation_threshold
            passes_confidence = signal.confidence >= self._min_confidence

            opp = Opportunity(
                signal=signal,
                passes_threshold=passes_threshold,
                passes_confidence=passes_confidence,
            )

            if opp.is_valid:
                opportunities.append(opp)
                log.info(
                    "Oportunidad detectada: %s %s | desviación=%.1f%% | confianza=%.0f%% | TP=%.1f%% SL=%.1f%%",
                    signal.direction,
                    signal.symbol,
                    signal.deviation_pct * 100,
                    signal.confidence * 100,
                    signal.take_profit_pct * 100,
                    signal.stop_loss_pct * 100,
                )

        log.info(
            "Ineficiencias: %d oportunidades de %d señales (umbral=%.0f%%, confianza_min=%.0f%%)",
            len(opportunities), len(signals),
            self._deviation_threshold * 100,
            self._min_confidence * 100,
        )
        return opportunities
