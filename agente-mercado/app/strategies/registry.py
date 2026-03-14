"""Registry de estrategias — configuracion centralizada.

Estrategias basadas en Oliver Vélez + Andrés Valdez (placeholder).
Las señales se generan por reglas técnicas, NO por LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.strategies.prompts import (
    IMPROVEMENT_ANALYSIS_PROMPT,
    LEARNING_REPORT_PROMPT,
    LESSON_BATCH_PROMPT,
)


@dataclass(frozen=True)
class StrategyConfig:
    """Configuracion inmutable de una estrategia."""

    id: str
    name: str
    description: str

    # Tipo de señal (patrón a detectar)
    signal_type: str  # "elephant_bar", "ignored_bar", "sma_pullback", "custom_rules"

    # Risk
    tp_min: float
    tp_max: float
    sl_min: float
    sl_max: float
    max_per_trade_pct: float
    deviation_threshold: float
    min_confidence: float
    max_concurrent_positions: int

    # Timing
    cycle_interval_minutes: int

    # --- Fields with defaults below ---
    enabled: bool = True

    # Timeframes requeridos para detección
    detection_timeframes: tuple[str, ...] = ("5m", "15m")
    trend_timeframe: str = "1h"

    # Pre-filter
    min_momentum: float = 0.3
    prefer_trending: bool = False

    # LLM budget share (reducido — solo para análisis post-trade)
    llm_budget_fraction: float = 0.25

    # Capital
    initial_capital_usd: float = 50.0

    # Learning
    trades_per_learning_report: int = 15
    trades_per_improvement_cycle: int = 20

    # OHLCV
    needs_ohlcv: bool = True  # Todas necesitan OHLCV ahora

    # Prompts LLM (solo para análisis, NO para señales)
    learning_report_prompt: str = LEARNING_REPORT_PROMPT
    lesson_batch_prompt: str = LESSON_BATCH_PROMPT
    improvement_prompt: str = IMPROVEMENT_ANALYSIS_PROMPT


STRATEGIES: dict[str, StrategyConfig] = {
    "oliver_elephant": StrategyConfig(
        id="oliver_elephant",
        name="Oliver Vélez — Velas Elefante",
        description=(
            "Detecta velas con cuerpo >=70% del rango total (alta convicción). "
            "Entry en ruptura del extremo, stop en el extremo opuesto. "
            "Filosofía: 'perder 1 vela, ganar 2-12 velas'."
        ),
        signal_type="elephant_bar",
        detection_timeframes=("5m", "15m"),
        trend_timeframe="1h",
        tp_min=0.02,
        tp_max=0.06,
        sl_min=0.005,
        sl_max=0.015,
        max_per_trade_pct=0.06,
        deviation_threshold=0.01,
        min_confidence=0.50,
        max_concurrent_positions=15,
        cycle_interval_minutes=5,
        min_momentum=0.3,
        prefer_trending=True,
        llm_budget_fraction=0.30,
    ),
    "oliver_sma": StrategyConfig(
        id="oliver_sma",
        name="Oliver Vélez — 20/200 SMA",
        description=(
            "Opera pullbacks a SMA20 en tendencias establecidas (SMA20 > SMA200 "
            "para alcista, SMA20 < SMA200 para bajista). Detecta Narrow State "
            "(SMAs convergentes) para movimientos explosivos."
        ),
        signal_type="sma_pullback",
        detection_timeframes=("15m",),
        trend_timeframe="1h",
        tp_min=0.02,
        tp_max=0.04,
        sl_min=0.008,
        sl_max=0.015,
        max_per_trade_pct=0.06,
        deviation_threshold=0.01,
        min_confidence=0.50,
        max_concurrent_positions=10,
        cycle_interval_minutes=10,
        min_momentum=0.5,
        prefer_trending=True,
        llm_budget_fraction=0.25,
    ),
    "oliver_ignored": StrategyConfig(
        id="oliver_ignored",
        name="Oliver Vélez — Barras Ignoradas",
        description=(
            "Detecta patrón GREEN-RED-GREEN (alcista) o RED-GREEN-RED (bajista). "
            "La barra del medio es 'ignorada' por el mercado — el movimiento "
            "continúa en la dirección original."
        ),
        signal_type="ignored_bar",
        detection_timeframes=("5m", "15m"),
        trend_timeframe="1h",
        tp_min=0.015,
        tp_max=0.04,
        sl_min=0.005,
        sl_max=0.015,
        max_per_trade_pct=0.06,
        deviation_threshold=0.01,
        min_confidence=0.45,
        max_concurrent_positions=15,
        cycle_interval_minutes=5,
        min_momentum=0.3,
        prefer_trending=True,
        llm_budget_fraction=0.20,
    ),
    "andres_valdez": StrategyConfig(
        id="andres_valdez",
        name="Andrés Valdez — Forex Strategy",
        description=(
            "Estrategia de Forex basada en la metodología de Andrés Valdez. "
            "Configuración pendiente — las reglas se definen en Strategy.params."
        ),
        enabled=False,
        signal_type="custom_rules",
        detection_timeframes=("15m", "1h"),
        trend_timeframe="1h",
        tp_min=0.01,
        tp_max=0.03,
        sl_min=0.005,
        sl_max=0.015,
        max_per_trade_pct=0.06,
        deviation_threshold=0.01,
        min_confidence=0.50,
        max_concurrent_positions=10,
        cycle_interval_minutes=10,
        min_momentum=0.3,
        prefer_trending=False,
        llm_budget_fraction=0.25,
    ),
}
