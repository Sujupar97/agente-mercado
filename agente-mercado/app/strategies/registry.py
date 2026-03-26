"""Registry de estrategias — Oliver Vélez (S1/S2) + SMC El Sensei (S3).

S1/S2: Pullback a EMA20 según el Plan de Trading de Oliver Vélez.
S3: Smart Money Concepts (Order Blocks, BOS/ChoCH, Liquidity Sweeps).
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
    """Configuración inmutable de una estrategia Forex."""

    id: str
    name: str
    description: str

    # Dirección y tipo
    signal_type: str  # "pullback_ema20_long" | "pullback_ema20_short" | "smc_institutional"
    direction: str  # "LONG" | "SHORT" | "BOTH"

    # Instrumentos que opera
    instruments: tuple[str, ...] = ("EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD")

    # Timeframes
    primary_timeframe: str = "H1"
    context_timeframe: str = "H4"
    entry_timeframe: str = "M1"  # Timeframe para buscar entradas (Oliver Vélez — M1 lo más cercano a M2)

    # Umbrales de entrada para pullback detector (M1/M5)
    entry_min_retrace_pct: float = 0.20  # 20% retrace (más bajo que H1)
    entry_ema20_zone_atr_mult: float = 0.50  # 0.50 ATR zone (más ancho que H1)

    # Risk
    risk_per_trade_pct: float = 0.01  # 1% del balance
    min_risk_reward: float = 2.0  # R:R mínimo 1:2
    max_concurrent_positions: int = 3
    max_trades_per_day: int = 0  # 0 = sin límite, >0 = máximo trades por día

    # Timing
    cycle_interval_minutes: int = 15  # Alineado a velas H1

    # Estado
    enabled: bool = True

    # Capital inicial (se sincroniza con broker al arrancar)
    initial_capital_usd: float = 5_500.0  # Sincroniza con balance real del broker

    # Learning
    trades_per_learning_report: int = 15
    trades_per_improvement_cycle: int = 20

    # LLM (solo post-trade)
    llm_budget_fraction: float = 0.50
    learning_report_prompt: str = LEARNING_REPORT_PROMPT
    lesson_batch_prompt: str = LESSON_BATCH_PROMPT
    improvement_prompt: str = IMPROVEMENT_ANALYSIS_PROMPT


STRATEGIES: dict[str, StrategyConfig] = {
    "s1_pullback_20_up": StrategyConfig(
        id="s1_pullback_20_up",
        name="S1 — Pullback EMA20 Alcista",
        description=(
            "Longs en pullback a EMA20 en tendencia alcista confirmada. "
            "Requiere 8 filtros de contexto (precio > SMA200, SMA200 UP, "
            "EMA20 > SMA200, no trap zone, etc). Patrones: BULL_ENGULFING, "
            "PIN_BAR_ALCISTA, GREEN_OVERPOWERS_RED. R:R mínimo 1:2."
        ),
        signal_type="pullback_ema20_long",
        direction="LONG",
    ),
    "s2_pullback_20_down": StrategyConfig(
        id="s2_pullback_20_down",
        name="S2 — Pullback EMA20 Bajista",
        description=(
            "Shorts en pullback a EMA20 en tendencia bajista confirmada. "
            "Requiere 8 filtros de contexto (precio < SMA200, SMA200 DOWN, "
            "EMA20 < SMA200, no trap zone, etc). Patrones: BEAR_ENGULFING, "
            "PIN_BAR_BAJISTA, RED_OVERPOWERS_GREEN. R:R mínimo 1:2."
        ),
        signal_type="pullback_ema20_short",
        direction="SHORT",
    ),
    "s3_smc_sensei": StrategyConfig(
        id="s3_smc_sensei",
        name="S3 — SMC El Sensei",
        description=(
            "Smart Money Concepts: Order Blocks + BOS/ChoCH + Liquidity Sweeps. "
            "Metodología institucional inspirada en El Sensei. BIAS multi-timeframe "
            "(D1 > H4 > H1), entradas en M5 con OB + confirmación de estructura. "
            "Máximo 1 trade por día. R:R mínimo 1:2."
        ),
        signal_type="smc_institutional",
        direction="BOTH",
        instruments=("EUR_USD", "GBP_USD", "USD_JPY"),
        entry_timeframe="M5",
        max_concurrent_positions=1,
        max_trades_per_day=1,
    ),
}
