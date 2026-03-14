"""Modelos ORM — tablas del agente multi-estrategia."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Market(Base):
    """Par o mercado escaneado por el agente."""

    __tablename__ = "markets"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # "binance" | "bybit" | "polymarket"
    symbol: Mapped[str] = mapped_column(String(32), index=True)  # "BTC/USDT"
    category: Mapped[str] = mapped_column(String(32), default="crypto")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    bid: Mapped[float] = mapped_column(Float, default=0.0)
    ask: Mapped[float] = mapped_column(Float, default=0.0)
    volume_24h: Mapped[float] = mapped_column(Float, default=0.0)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    last_scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Strategy(Base):
    """Definicion de una estrategia de trading."""

    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status_text: Mapped[str] = mapped_column(Text, default="Iniciando...")
    llm_budget_fraction: Mapped[float] = mapped_column(Float, default=0.25)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Signal(Base):
    """Señal generada por el LLM + análisis cuantitativo."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True, default="momentum")
    market_id: Mapped[str] = mapped_column(String(256), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    estimated_value: Mapped[float] = mapped_column(Float)
    market_price: Mapped[float] = mapped_column(Float)
    deviation_pct: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(16))  # "BUY" | "SELL"
    confidence: Mapped[float] = mapped_column(Float)  # 0.0-1.0
    take_profit_pct: Mapped[float] = mapped_column(Float)
    stop_loss_pct: Mapped[float] = mapped_column(Float)
    llm_model: Mapped[str] = mapped_column(String(64))
    llm_prompt_hash: Mapped[str] = mapped_column(String(64))
    llm_response_summary: Mapped[str] = mapped_column(Text)
    data_sources_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Trade(Base):
    """Operación ejecutada (real o simulada)."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True, default="momentum")
    signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    market_id: Mapped[str] = mapped_column(String(256), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(16))  # "BUY" | "SELL"
    size_usd: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    kelly_fraction: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        String(16), default="OPEN"
    )  # OPEN | CLOSED | CANCELLED | FAILED
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_simulation: Mapped[bool] = mapped_column(default=False)

    # Position management (Oliver Vélez)
    scale_ins: Mapped[int] = mapped_column(Integer, default=0)
    partial_exits: Mapped[int] = mapped_column(Integer, default=0)
    original_size_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pattern_name: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentState(Base):
    """Estado del agente por estrategia."""

    __tablename__ = "agent_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True, default="momentum")
    mode: Mapped[str] = mapped_column(String(16), default="SIMULATION")
    capital_usd: Mapped[float] = mapped_column(Float, default=50.0)
    peak_capital_usd: Mapped[float] = mapped_column(Float, default=50.0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_costs: Mapped[float] = mapped_column(Float, default=0.0)
    positions_open: Mapped[int] = mapped_column(Integer, default=0)
    markets_scanned_total: Mapped[int] = mapped_column(Integer, default=0)
    trades_executed_total: Mapped[int] = mapped_column(Integer, default=0)
    trades_won: Mapped[int] = mapped_column(Integer, default=0)
    trades_lost: Mapped[int] = mapped_column(Integer, default=0)
    last_cycle_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_trade_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_loss_days: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CostLog(Base):
    """Registro de costos operativos (LLM, APIs, fees de trading)."""

    __tablename__ = "cost_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cost_type: Mapped[str] = mapped_column(String(32))  # "llm" | "api" | "trading_fee"
    provider: Mapped[str] = mapped_column(String(64))  # "gemini" | "binance" | etc.
    amount_usd: Mapped[float] = mapped_column(Float)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SignalOutcome(Base):
    """Resultado real de una senal — calculado al cerrar el trade."""

    __tablename__ = "signal_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True, default="momentum")
    signal_id: Mapped[int] = mapped_column(Integer, index=True)
    trade_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    predicted_confidence: Mapped[float] = mapped_column(Float)
    predicted_deviation: Mapped[float] = mapped_column(Float)
    predicted_tp_pct: Mapped[float] = mapped_column(Float)
    predicted_sl_pct: Mapped[float] = mapped_column(Float)
    actual_pnl: Mapped[float] = mapped_column(Float)
    actual_return_pct: Mapped[float] = mapped_column(Float)
    hit_tp: Mapped[bool] = mapped_column(default=False)
    hold_duration_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    llm_model: Mapped[str] = mapped_column(String(64))
    hour_of_day: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LearningLog(Base):
    """Registro de ajustes automaticos del sistema de aprendizaje."""

    __tablename__ = "learning_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True, default="momentum")
    adjustment_type: Mapped[str] = mapped_column(String(32))
    parameter: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    new_value: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    trades_analyzed: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Bitacora(Base):
    """Bitacora detallada por trade — el diario de trading."""

    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, index=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(16))

    # Contexto de entrada (se llena al abrir el trade)
    entry_reasoning: Mapped[str] = mapped_column(Text)
    market_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    entry_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Contexto de salida (se llena al cerrar el trade)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    hold_duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Leccion (generada por LLM en batch)
    lesson: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LearningReport(Base):
    """Reporte de aprendizaje periodico — generado cada N trades por estrategia."""

    __tablename__ = "learning_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    report_number: Mapped[int] = mapped_column(Integer)
    trades_analyzed: Mapped[int] = mapped_column(Integer)

    # Contenido generado por LLM
    analysis: Mapped[str] = mapped_column(Text)
    patterns_found: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Snapshot de estadisticas
    stats_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ImprovementCycle(Base):
    """Ciclo de mejora de 20 trades — identifica el patrón de pérdida #1."""

    __tablename__ = "improvement_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    cycle_number: Mapped[int] = mapped_column(Integer)
    trades_in_cycle: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(16), default="active"
    )  # active | analyzing | completed

    # Resultado del análisis LLM
    loss_pattern_identified: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_created_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ImprovementRule(Base):
    """Regla permanente generada por el ciclo de mejora — IRREVOCABLE."""

    __tablename__ = "improvement_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    cycle_number: Mapped[int] = mapped_column(Integer)
    rule_type: Mapped[str] = mapped_column(String(32))  # time_filter, pattern_filter, etc.

    # Descripción legible
    description: Mapped[str] = mapped_column(Text)
    pattern_name: Mapped[str] = mapped_column(String(64))

    # Condiciones evaluables programáticamente
    condition_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Estadísticas pre-regla
    trades_before_rule: Mapped[int] = mapped_column(Integer, default=0)
    win_rate_before: Mapped[float] = mapped_column(Float, default=0.0)

    # Siempre activa — las reglas son PERMANENTES
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
