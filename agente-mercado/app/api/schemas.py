"""Schemas de respuesta Pydantic para la API REST."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AgentStatus(BaseModel):
    mode: str
    capital_usd: float
    initial_capital_usd: float
    peak_capital_usd: float
    capital_in_positions: float
    total_pnl: float
    total_costs: float
    net_profit: float
    net_7d: float
    net_14d: float
    win_rate: float
    drawdown_pct: float
    positions_open: int
    trades_won: int
    trades_lost: int
    markets_scanned_total: int
    trades_executed_total: int
    last_cycle_at: datetime | None
    cycle_interval_minutes: int
    llm_usage: dict
    base_capital_usd: float | None = None
    next_threshold_usd: float | None = None
    risk_per_trade_usd: float | None = None
    survival_status: str | None = None
    survival_reason: str | None = None


class PositionOut(BaseModel):
    id: int
    symbol: str
    direction: str
    size_usd: float
    entry_price: float
    take_profit_price: float | None
    stop_loss_price: float | None
    kelly_fraction: float
    is_simulation: bool
    created_at: datetime


class TradeOut(BaseModel):
    id: int
    symbol: str
    direction: str
    size_usd: float
    entry_price: float
    exit_price: float | None
    pnl: float | None
    fees: float
    status: str
    kelly_fraction: float
    is_simulation: bool
    created_at: datetime
    closed_at: datetime | None


class SignalOut(BaseModel):
    id: int
    symbol: str
    direction: str
    confidence: float
    deviation_pct: float
    take_profit_pct: float
    stop_loss_pct: float
    llm_model: str
    llm_response_summary: str
    created_at: datetime


class ConfigUpdate(BaseModel):
    deviation_threshold: float | None = None
    fractional_kelly: float | None = None
    max_per_trade_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_weekly_loss_pct: float | None = None
    max_drawdown_pct: float | None = None
    max_concurrent_positions: int | None = None
    min_volume_usd: float | None = None
    min_confidence: float | None = None
    cycle_interval_minutes: int | None = None


class CycleResponse(BaseModel):
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str
    mode: str
    uptime_seconds: float


# --- Dashboard Schemas ---

class DailyPnL(BaseModel):
    """P&L diario para gráfica histórica."""
    date: str  # YYYY-MM-DD
    capital: float
    pnl: float
    costs: float
    net: float
    trades_count: int


class PnLHistoryResponse(BaseModel):
    """Respuesta del endpoint /stats/pnl-history."""
    history: list[DailyPnL]


class AddCapitalRequest(BaseModel):
    """Request para añadir capital simulado."""
    amount_usd: float


class AddCapitalResponse(BaseModel):
    """Respuesta al añadir capital simulado."""
    success: bool
    message: str
    new_capital: float


class LLMUsageResponse(BaseModel):
    """Uso detallado del LLM."""
    rpm: int
    rpm_limit: int
    rpd: int
    rpd_limit: int
    rpm_percent: float
    rpd_percent: float


# --- Learning Schemas ---

class SymbolPerformanceOut(BaseModel):
    """Rendimiento por simbolo."""
    symbol: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float
    avg_hold_minutes: float


class DirectionStatsOut(BaseModel):
    """Rendimiento por direccion."""
    direction: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float


class CalibrationBucketOut(BaseModel):
    """Calibracion de confianza."""
    confidence_range: str
    predicted_win_rate: float
    actual_win_rate: float
    trade_count: int
    calibration_error: float


class ModelComparisonOut(BaseModel):
    """Comparacion de modelos LLM."""
    model: str
    total_trades: int
    wins: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float


class PerformanceResponse(BaseModel):
    """Reporte completo de rendimiento."""
    total_trades: int
    win_rate: float
    profit_factor: float
    sortino_ratio: float
    expectancy: float
    best_symbols: list[SymbolPerformanceOut]
    worst_symbols: list[SymbolPerformanceOut]
    calibration: list[CalibrationBucketOut]
    buy_stats: DirectionStatsOut | None
    sell_stats: DirectionStatsOut | None
    best_hours: list[int]
    worst_hours: list[int]
    model_comparison: list[ModelComparisonOut]
    recommendations: list[str]
    data_sufficient: bool = True


class AdjustmentOut(BaseModel):
    """Ajuste adaptativo activo."""
    type: str
    reason: str
    symbol: str = ""
    direction: str = ""
    hour: int = -1
    new_value: float = 0.0


class LearningLogOut(BaseModel):
    """Entrada del log de aprendizaje."""
    id: int
    adjustment_type: str
    parameter: str
    old_value: str | None
    new_value: str
    reason: str
    trades_analyzed: int
    created_at: datetime


# --- Multi-Strategy Schemas ---

class StrategyOut(BaseModel):
    """Estrategia con su estado actual."""
    id: str
    name: str
    description: str
    enabled: bool
    status_text: str
    llm_budget_fraction: float
    capital_usd: float
    peak_capital_usd: float
    total_pnl: float
    positions_open: int
    trades_won: int
    trades_lost: int
    win_rate: float
    mode: str
    last_trade_at: datetime | None
    broker_balance: float | None = None
    base_capital_usd: float | None = None
    next_threshold_usd: float | None = None
    risk_per_trade_usd: float | None = None
    improvement_cycle: CycleProgressOut | None = None
    active_rules_count: int = 0


class BitacoraOut(BaseModel):
    """Entrada de bitacora (diario de trading)."""
    id: int
    trade_id: int
    strategy_id: str
    symbol: str
    direction: str
    entry_reasoning: str
    market_context: dict | None
    entry_price: float
    entry_time: datetime
    exit_reason: str | None
    exit_price: float | None
    exit_time: datetime | None
    pnl: float | None
    hold_duration_minutes: float | None
    lesson: str | None
    created_at: datetime


class LearningReportOut(BaseModel):
    """Reporte de aprendizaje interpretativo."""
    id: int
    strategy_id: str
    report_number: int
    trades_analyzed: int
    analysis: str
    patterns_found: list | None
    recommendations: list | None
    stats_snapshot: dict | None
    created_at: datetime


# --- Improvement System Schemas ---

class ImprovementCycleOut(BaseModel):
    """Ciclo de mejora de 20 trades."""
    id: int
    strategy_id: str
    cycle_number: int
    trades_in_cycle: int
    status: str
    loss_pattern_identified: str | None
    rule_created_id: int | None
    started_at: datetime
    completed_at: datetime | None


class ImprovementRuleOut(BaseModel):
    """Regla de mejora permanente."""
    id: int
    strategy_id: str
    cycle_number: int
    rule_type: str
    description: str
    pattern_name: str
    condition_json: dict | None
    trades_before_rule: int
    win_rate_before: float
    is_active: bool
    created_at: datetime


class CycleProgressOut(BaseModel):
    """Progreso del ciclo de mejora activo."""
    cycle_number: int
    trades_in_cycle: int
    trades_needed: int
    status: str


# --- Broker Schemas ---

class BrokerAccountOut(BaseModel):
    """Estado de la cuenta del broker."""
    balance: float
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    equity: float
    open_trades: int
    connected: bool


class BrokerPositionOut(BaseModel):
    """Posición abierta en el broker."""
    trade_id: str
    instrument: str
    units: float
    direction: str
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None
    take_profit: float | None


class BrokerSyncStatusOut(BaseModel):
    """Estado de sincronización local vs broker."""
    last_sync_at: datetime | None
    local_open_trades: int
    broker_open_trades: int
    discrepancies: list[dict]
    is_synced: bool


class SyncResultOut(BaseModel):
    """Resultado de una sincronización forzada."""
    success: bool
    message: str
    trades_synced: int
    discrepancies_found: int


# --- Market State Schemas ---

class FilterStatusOut(BaseModel):
    """Estado de un filtro de contexto."""
    name: str
    passed: bool


class MarketStateOut(BaseModel):
    """Estado del mercado para un instrumento."""
    instrument: str
    timeframe: str
    timestamp: datetime | None
    price: float
    sma200: float
    ema20: float
    atr14: float
    trend_state: str
    price_vs_sma200: str
    sma200_slope: str
    ema20_slope: str
    ma_state: str
    ema20_vs_sma200: str
    trap_zone: bool
    last_swing_high: float
    last_swing_low: float
    impulse_range: float
    filters_long: list[FilterStatusOut]
    filters_short: list[FilterStatusOut]


class AllMarketStatesOut(BaseModel):
    """Estado del mercado para todos los instrumentos."""
    session_active: bool
    current_session: str | None
    market_open: bool
    instruments: list[MarketStateOut]


# --- Trade Chart Schemas ---

class ChartCandleOut(BaseModel):
    """Una vela OHLCV para el gráfico."""
    time: int  # Unix timestamp (seconds)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class TradeMarkerOut(BaseModel):
    """Marcador sobre el gráfico (entrada, salida, SL, TP)."""
    time: int  # Unix timestamp (seconds)
    position: str  # "aboveBar" | "belowBar"
    color: str
    shape: str  # "arrowUp" | "arrowDown" | "circle"
    text: str


class TradePriceLine(BaseModel):
    """Línea horizontal de precio (SL, TP, entry)."""
    price: float
    color: str
    line_style: int  # 0=solid, 1=dashed, 2=dotted
    label: str


class TradeChartDataOut(BaseModel):
    """Datos completos para renderizar el gráfico de un trade."""
    trade_id: int
    symbol: str
    direction: str
    timeframe: str
    status: str
    entry_price: float
    exit_price: float | None
    stop_loss: float | None
    take_profit: float | None
    pnl: float | None
    pattern_name: str | None
    entry_time: str | None
    exit_time: str | None
    risk_reward: float | None = None
    entry_reasoning: str | None = None
    exit_reason: str | None = None
    market_context: dict | None = None
    candles: list[ChartCandleOut]
    markers: list[TradeMarkerOut]
    price_lines: list[TradePriceLine]
