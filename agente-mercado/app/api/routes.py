"""Endpoints REST del agente."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_token, verify_token
from app.api.schemas import (
    AddCapitalRequest,
    AddCapitalResponse,
    AdjustmentOut,
    AgentStatus,
    AllMarketStatesOut,
    BitacoraOut,
    BrokerAccountOut,
    BrokerPositionOut,
    BrokerSyncStatusOut,
    CalibrationBucketOut,
    ChartCandleOut,
    ConfigUpdate,
    CycleProgressOut,
    CycleResponse,
    DailyPnL,
    DirectionStatsOut,
    FilterStatusOut,
    HealthResponse,
    ImprovementCycleOut,
    ImprovementRuleOut,
    LearningLogOut,
    LearningReportOut,
    LLMUsageResponse,
    MarketStateOut,
    ModelComparisonOut,
    PerformanceResponse,
    PnLHistoryResponse,
    PositionOut,
    SignalOut,
    StrategyOut,
    SymbolPerformanceOut,
    SyncResultOut,
    TradeChartDataOut,
    TradeMarkerOut,
    TradeOut,
    TradePriceLine,
)
from app.broker.base import BrokerInterface
from app.config import settings
from app.core.state import StateManager
from app.db.database import get_session
from app.db.models import AgentState, Bitacora, BrokerSyncLog, CostLog, ImprovementCycle, LearningLog, LearningReport, Signal, Strategy, Trade
from app.forex.sessions import get_current_session, is_forex_market_open, is_trading_session
from app.learning.adaptive import AdaptiveFilter
from app.learning.improvement_engine import ImprovementEngine
from app.learning.performance import PerformanceAnalyzer
from app.llm.budget import LLMBudget
from app.pnl.calculator import PnLCalculator
from app.signals.context_filters import ContextFilterEngine
from app.signals.market_state import MarketStateAnalyzer

router = APIRouter()
_start_time = time.monotonic()


# --- Públicos (sin auth) ---


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_session)):
    state_mgr = StateManager(session)
    state = await state_mgr.get_state()
    return HealthResponse(
        status="ok",
        mode=state.mode if state else "UNKNOWN",
        uptime_seconds=round(time.monotonic() - _start_time, 1),
    )


# --- Protegidos (JWT) ---


@router.get("/status", response_model=AgentStatus)
async def get_status(
    session: AsyncSession = Depends(get_session),
):
    # Sumar capital de TODAS las estrategias (no de "momentum")
    states_result = await session.execute(select(AgentState))
    all_states = states_result.scalars().all()

    total_capital = sum(s.capital_usd for s in all_states) if all_states else 0.0
    total_peak = sum(s.peak_capital_usd for s in all_states) if all_states else 0.0
    total_positions_open = sum(s.positions_open for s in all_states) if all_states else 0
    total_trades_won = sum(s.trades_won for s in all_states) if all_states else 0
    total_trades_lost = sum(s.trades_lost for s in all_states) if all_states else 0
    total_scanned = sum(s.markets_scanned_total for s in all_states) if all_states else 0
    total_executed = sum(s.trades_executed_total for s in all_states) if all_states else 0
    last_cycle = max((s.last_cycle_at for s in all_states if s.last_cycle_at), default=None)
    mode = all_states[0].mode if all_states else "SIMULATION"

    pnl_calc = PnLCalculator(session)
    budget = LLMBudget()
    summary = await pnl_calc.get_summary()
    llm_usage = await budget.get_usage()
    await budget.close()

    # Capital invertido en posiciones abiertas
    positions_result = await session.execute(
        select(func.coalesce(func.sum(Trade.size_usd), 0.0))
        .where(Trade.status == "OPEN")
    )
    capital_in_positions = float(positions_result.scalar() or 0.0)

    # Drawdown global
    drawdown_pct = 0.0
    if total_peak > 0:
        drawdown_pct = round((1 - total_capital / total_peak) * 100, 2)

    return AgentStatus(
        mode=mode,
        capital_usd=total_capital,
        initial_capital_usd=total_capital,  # Usar capital actual como referencia
        peak_capital_usd=total_peak,
        capital_in_positions=round(capital_in_positions, 2),
        total_pnl=summary["total_pnl"],
        total_costs=summary["total_costs"],
        net_profit=summary["net_profit"],
        net_7d=summary["net_7d"],
        net_14d=summary["net_14d"],
        win_rate=summary["win_rate"],
        drawdown_pct=max(drawdown_pct, 0.0),
        positions_open=total_positions_open,
        trades_won=total_trades_won,
        trades_lost=total_trades_lost,
        markets_scanned_total=total_scanned,
        trades_executed_total=total_executed,
        last_cycle_at=last_cycle,
        cycle_interval_minutes=settings.cycle_interval_minutes,
        llm_usage=llm_usage,
        survival_status="CONTINUE",
        survival_reason=None,
    )


@router.get("/positions", response_model=list[PositionOut])
async def get_positions(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    result = await session.execute(
        select(Trade).where(Trade.status == "OPEN").order_by(Trade.created_at.desc())
    )
    trades = result.scalars().all()
    return [
        PositionOut(
            id=t.id,
            symbol=t.symbol,
            direction=t.direction,
            size_usd=t.size_usd,
            entry_price=t.entry_price,
            take_profit_price=t.take_profit_price,
            stop_loss_price=t.stop_loss_price,
            kelly_fraction=t.kelly_fraction,
            is_simulation=t.is_simulation,
            created_at=t.created_at,
        )
        for t in trades
    ]


@router.get("/trades", response_model=list[TradeOut])
async def get_trades(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    winner: bool | None = None,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    query = select(Trade)

    # Filtros opcionales
    if status:
        query = query.where(Trade.status == status.upper())

    if winner is not None:
        if winner:
            query = query.where(Trade.pnl > 0)
        else:
            query = query.where(Trade.pnl <= 0)

    query = query.order_by(Trade.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    trades = result.scalars().all()
    return [
        TradeOut(
            id=t.id,
            symbol=t.symbol,
            direction=t.direction,
            size_usd=t.size_usd,
            entry_price=t.entry_price,
            exit_price=t.exit_price,
            pnl=t.pnl,
            fees=t.fees,
            status=t.status,
            kelly_fraction=t.kelly_fraction,
            is_simulation=t.is_simulation,
            created_at=t.created_at,
            closed_at=t.closed_at,
        )
        for t in trades
    ]


@router.get("/signals", response_model=list[SignalOut])
async def get_signals(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    result = await session.execute(
        select(Signal).order_by(Signal.created_at.desc()).limit(limit)
    )
    signals = result.scalars().all()
    return [
        SignalOut(
            id=s.id,
            symbol=s.symbol,
            direction=s.direction,
            confidence=s.confidence,
            deviation_pct=s.deviation_pct,
            take_profit_pct=s.take_profit_pct,
            stop_loss_pct=s.stop_loss_pct,
            llm_model=s.llm_model,
            llm_response_summary=s.llm_response_summary,
            created_at=s.created_at,
        )
        for s in signals
    ]


@router.post("/cycle", response_model=CycleResponse)
async def force_cycle(
    _user: str = Depends(verify_token),
):
    """Fuerza un ciclo manual del agente."""
    from app.core.scheduler import trigger_manual_cycle

    try:
        await trigger_manual_cycle()
        return CycleResponse(status="ok", message="Ciclo ejecutado manualmente")
    except Exception as e:
        return CycleResponse(status="error", message=str(e))


@router.post("/agent/start", response_model=CycleResponse)
async def start_agent(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    state_mgr = StateManager(session)
    await state_mgr.set_mode(settings.agent_mode)
    return CycleResponse(
        status="ok", message=f"Agente iniciado en modo {settings.agent_mode}"
    )


@router.post("/agent/stop", response_model=CycleResponse)
async def stop_agent(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    state_mgr = StateManager(session)
    await state_mgr.set_mode("PAUSED")
    return CycleResponse(status="ok", message="Agente pausado")


@router.put("/config", response_model=CycleResponse)
async def update_config(
    config: ConfigUpdate,
    _user: str = Depends(verify_token),
):
    """Actualiza parámetros del agente en runtime."""
    updated = []
    if config.deviation_threshold is not None:
        settings.deviation_threshold = config.deviation_threshold
        updated.append(f"deviation_threshold={config.deviation_threshold}")
    if config.fractional_kelly is not None:
        settings.fractional_kelly = config.fractional_kelly
        updated.append(f"fractional_kelly={config.fractional_kelly}")
    if config.max_per_trade_pct is not None:
        settings.max_per_trade_pct = config.max_per_trade_pct
        updated.append(f"max_per_trade_pct={config.max_per_trade_pct}")
    if config.max_daily_loss_pct is not None:
        settings.max_daily_loss_pct = config.max_daily_loss_pct
        updated.append(f"max_daily_loss_pct={config.max_daily_loss_pct}")
    if config.max_weekly_loss_pct is not None:
        settings.max_weekly_loss_pct = config.max_weekly_loss_pct
        updated.append(f"max_weekly_loss_pct={config.max_weekly_loss_pct}")
    if config.max_drawdown_pct is not None:
        settings.max_drawdown_pct = config.max_drawdown_pct
        updated.append(f"max_drawdown_pct={config.max_drawdown_pct}")
    if config.max_concurrent_positions is not None:
        settings.max_concurrent_positions = config.max_concurrent_positions
        updated.append(f"max_concurrent_positions={config.max_concurrent_positions}")
    if config.min_volume_usd is not None:
        settings.min_volume_usd = config.min_volume_usd
        updated.append(f"min_volume_usd={config.min_volume_usd}")
    if config.min_confidence is not None:
        settings.min_confidence = config.min_confidence
        updated.append(f"min_confidence={config.min_confidence}")

    return CycleResponse(
        status="ok",
        message=f"Actualizado: {', '.join(updated)}" if updated else "Sin cambios",
    )


@router.get("/stats/pnl-history", response_model=PnLHistoryResponse)
async def get_pnl_history(
    days: int = 30,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Retorna P&L histórico diario agregado para la gráfica."""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Agregar trades cerrados por día
    trades_by_day = await session.execute(
        select(
            cast(Trade.closed_at, Date).label("date"),
            func.sum(Trade.pnl).label("pnl"),
            func.count(Trade.id).label("trades_count"),
        )
        .where(
            Trade.status == "CLOSED",
            Trade.closed_at >= start_date,
        )
        .group_by(cast(Trade.closed_at, Date))
        .order_by(cast(Trade.closed_at, Date))
    )
    trades_data = trades_by_day.all()

    # Agregar costos por día
    costs_by_day = await session.execute(
        select(
            cast(CostLog.created_at, Date).label("date"),
            func.sum(CostLog.amount_usd).label("costs"),
        )
        .where(CostLog.created_at >= start_date)
        .group_by(cast(CostLog.created_at, Date))
        .order_by(cast(CostLog.created_at, Date))
    )
    costs_data = {row.date: row.costs for row in costs_by_day.all()}

    # Obtener estado actual
    state_result = await session.execute(select(AgentState).where(AgentState.strategy_id == "momentum"))
    state = state_result.scalar_one_or_none()
    current_capital = state.capital_usd if state else settings.initial_capital_usd

    # Construir historial desde el final hacia atrás
    history = []
    running_capital = current_capital
    trades_dict = {row.date: (row.pnl or 0, row.trades_count) for row in trades_data}

    # Generar días completos
    for i in range(days):
        date = (datetime.now(timezone.utc) - timedelta(days=i)).date()
        date_str = date.isoformat()

        pnl = trades_dict.get(date, (0, 0))[0]
        trades_count = trades_dict.get(date, (0, 0))[1]
        costs = costs_data.get(date, 0)
        net = pnl - costs

        history.insert(
            0,
            DailyPnL(
                date=date_str,
                capital=round(running_capital, 2),
                pnl=round(pnl, 2),
                costs=round(costs, 4),
                net=round(net, 2),
                trades_count=trades_count,
            ),
        )

        # Capital del día anterior = capital actual - ganancia neta del día
        running_capital -= net

    return PnLHistoryResponse(history=history)


@router.post("/simulation/add-capital", response_model=AddCapitalResponse)
async def add_simulation_capital(
    request: AddCapitalRequest,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Añade capital simulado (solo en modo SIMULATION)."""
    import logging

    log = logging.getLogger("agente-mercado")

    state_mgr = StateManager(session)
    state = await state_mgr.get_state()

    if not state:
        return AddCapitalResponse(
            success=False,
            message="Estado del agente no encontrado",
            new_capital=0,
        )

    if state.mode != "SIMULATION":
        return AddCapitalResponse(
            success=False,
            message=f"Solo permitido en modo SIMULATION (actual: {state.mode})",
            new_capital=state.capital_usd,
        )

    if request.amount_usd <= 0:
        return AddCapitalResponse(
            success=False,
            message="Monto debe ser positivo",
            new_capital=state.capital_usd,
        )

    # Actualizar capital
    new_capital = state.capital_usd + request.amount_usd
    await session.execute(
        update(AgentState).where(AgentState.strategy_id == "momentum").values(capital_usd=new_capital)
    )
    await session.commit()

    log.info("Capital simulado añadido: +$%.2f → $%.2f", request.amount_usd, new_capital)

    return AddCapitalResponse(
        success=True,
        message=f"${request.amount_usd} añadidos exitosamente",
        new_capital=new_capital,
    )


@router.get("/llm-usage", response_model=LLMUsageResponse)
async def get_llm_usage(
    _user: str = Depends(verify_token),
):
    """Retorna uso detallado del LLM (separado de /status)."""
    budget = LLMBudget()
    usage = await budget.get_usage()
    await budget.close()

    rpm_percent = (
        (usage["rpm"] / usage["rpm_limit"] * 100) if usage["rpm_limit"] > 0 else 0
    )
    rpd_percent = (
        (usage["rpd"] / usage["rpd_limit"] * 100) if usage["rpd_limit"] > 0 else 0
    )

    return LLMUsageResponse(
        rpm=usage["rpm"],
        rpm_limit=usage["rpm_limit"],
        rpd=usage["rpd"],
        rpd_limit=usage["rpd_limit"],
        rpm_percent=round(rpm_percent, 1),
        rpd_percent=round(rpd_percent, 1),
    )


@router.post("/token")
async def generate_token():
    """Genera un token JWT para acceder a la API.

    NOTA: En producción, esto debería requerir autenticación previa.
    Para desarrollo, genera tokens libremente.
    """
    token = create_token()
    return {"access_token": token, "token_type": "bearer"}


# --- Learning Endpoints ---


@router.get("/learning/performance", response_model=PerformanceResponse)
async def get_performance_report(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Reporte completo de rendimiento con desglose."""
    analyzer = PerformanceAnalyzer(session)
    report = await analyzer.get_full_report()

    if not report:
        total = await analyzer.get_outcomes_count()
        return PerformanceResponse(
            total_trades=total,
            win_rate=0,
            profit_factor=0,
            sortino_ratio=0,
            expectancy=0,
            best_symbols=[],
            worst_symbols=[],
            calibration=[],
            buy_stats=None,
            sell_stats=None,
            best_hours=[],
            worst_hours=[],
            model_comparison=[],
            recommendations=[f"Datos insuficientes: {total}/30 trades cerrados con signal_id"],
            data_sufficient=False,
        )

    return PerformanceResponse(
        total_trades=report.total_trades,
        win_rate=report.win_rate,
        profit_factor=report.profit_factor,
        sortino_ratio=report.sortino_ratio,
        expectancy=report.expectancy,
        best_symbols=[
            SymbolPerformanceOut(
                symbol=s.symbol, total_trades=s.total_trades,
                wins=s.wins, losses=s.losses, win_rate=s.win_rate,
                total_pnl=round(s.total_pnl, 4), avg_pnl=round(s.avg_pnl, 4),
                profit_factor=round(s.profit_factor, 2),
                avg_hold_minutes=round(s.avg_hold_minutes, 1),
            )
            for s in report.best_symbols
        ],
        worst_symbols=[
            SymbolPerformanceOut(
                symbol=s.symbol, total_trades=s.total_trades,
                wins=s.wins, losses=s.losses, win_rate=s.win_rate,
                total_pnl=round(s.total_pnl, 4), avg_pnl=round(s.avg_pnl, 4),
                profit_factor=round(s.profit_factor, 2),
                avg_hold_minutes=round(s.avg_hold_minutes, 1),
            )
            for s in report.worst_symbols
        ],
        calibration=[
            CalibrationBucketOut(
                confidence_range=c.confidence_range,
                predicted_win_rate=round(c.predicted_win_rate, 3),
                actual_win_rate=round(c.actual_win_rate, 3),
                trade_count=c.trade_count,
                calibration_error=round(c.calibration_error, 3),
            )
            for c in report.calibration
        ],
        buy_stats=DirectionStatsOut(
            direction=report.buy_stats.direction,
            total_trades=report.buy_stats.total_trades,
            wins=report.buy_stats.wins, losses=report.buy_stats.losses,
            win_rate=report.buy_stats.win_rate,
            total_pnl=round(report.buy_stats.total_pnl, 4),
            avg_pnl=round(report.buy_stats.avg_pnl, 4),
            profit_factor=round(report.buy_stats.profit_factor, 2),
        ) if report.buy_stats else None,
        sell_stats=DirectionStatsOut(
            direction=report.sell_stats.direction,
            total_trades=report.sell_stats.total_trades,
            wins=report.sell_stats.wins, losses=report.sell_stats.losses,
            win_rate=report.sell_stats.win_rate,
            total_pnl=round(report.sell_stats.total_pnl, 4),
            avg_pnl=round(report.sell_stats.avg_pnl, 4),
            profit_factor=round(report.sell_stats.profit_factor, 2),
        ) if report.sell_stats else None,
        best_hours=report.best_hours,
        worst_hours=report.worst_hours,
        model_comparison=[
            ModelComparisonOut(
                model=m.model, total_trades=m.total_trades,
                wins=m.wins, win_rate=m.win_rate,
                total_pnl=round(m.total_pnl, 4),
                avg_pnl=round(m.avg_pnl, 4),
                profit_factor=round(m.profit_factor, 2),
            )
            for m in report.model_comparison
        ],
        recommendations=report.recommendations,
    )


@router.get("/learning/calibration", response_model=list[CalibrationBucketOut])
async def get_calibration(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Calibracion de confianza: predicho vs real."""
    analyzer = PerformanceAnalyzer(session)
    buckets = await analyzer.get_confidence_calibration()
    return [
        CalibrationBucketOut(
            confidence_range=c.confidence_range,
            predicted_win_rate=round(c.predicted_win_rate, 3),
            actual_win_rate=round(c.actual_win_rate, 3),
            trade_count=c.trade_count,
            calibration_error=round(c.calibration_error, 3),
        )
        for c in buckets
    ]


@router.get("/learning/symbols", response_model=list[SymbolPerformanceOut])
async def get_symbol_performance(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Rendimiento por simbolo (ranking)."""
    analyzer = PerformanceAnalyzer(session)
    stats = await analyzer.get_symbol_performance()
    result = [
        SymbolPerformanceOut(
            symbol=s.symbol, total_trades=s.total_trades,
            wins=s.wins, losses=s.losses, win_rate=s.win_rate,
            total_pnl=round(s.total_pnl, 4), avg_pnl=round(s.avg_pnl, 4),
            profit_factor=round(s.profit_factor, 2),
            avg_hold_minutes=round(s.avg_hold_minutes, 1),
        )
        for s in stats.values()
    ]
    result.sort(key=lambda x: x.total_pnl, reverse=True)
    return result


@router.get("/learning/adjustments", response_model=list[AdjustmentOut])
async def get_active_adjustments(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Ajustes adaptativos calculados."""
    adaptive = AdaptiveFilter(session)
    adjustments = await adaptive.compute_adjustments()
    return [
        AdjustmentOut(
            type=a.type, reason=a.reason, symbol=a.symbol,
            direction=a.direction, hour=a.hour, new_value=a.new_value,
        )
        for a in adjustments
    ]


@router.get("/learning/log", response_model=list[LearningLogOut])
async def get_learning_log(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Historial de ajustes realizados por el sistema."""
    result = await session.execute(
        select(LearningLog).order_by(LearningLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return [
        LearningLogOut(
            id=l.id,
            adjustment_type=l.adjustment_type,
            parameter=l.parameter,
            old_value=l.old_value,
            new_value=l.new_value,
            reason=l.reason,
            trades_analyzed=l.trades_analyzed,
            created_at=l.created_at,
        )
        for l in logs
    ]


# --- Multi-Strategy Endpoints ---


@router.get("/strategies", response_model=list[StrategyOut])
async def get_strategies(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Lista todas las estrategias con su estado actual."""
    result = await session.execute(select(Strategy).order_by(Strategy.id))
    strategies = result.scalars().all()

    out = []
    improvement_engine = ImprovementEngine(session)

    for s in strategies:
        # Obtener AgentState de esta estrategia
        state_result = await session.execute(
            select(AgentState).where(AgentState.strategy_id == s.id)
        )
        state = state_result.scalar_one_or_none()

        total = (state.trades_won + state.trades_lost) if state else 0
        wr = state.trades_won / total if total > 0 else 0.0

        # Cross-check: positions_open desde Trade table (fuente de verdad)
        actual_open_result = await session.execute(
            select(func.count(Trade.id)).where(
                Trade.strategy_id == s.id,
                Trade.status == "OPEN",
            )
        )
        actual_open = actual_open_result.scalar() or 0
        if state and state.positions_open != actual_open:
            state.positions_open = actual_open

        # Obtener progreso del ciclo de mejora
        cycle_progress = None
        active_rules_count = 0
        try:
            cp = await improvement_engine.get_cycle_progress(s.id)
            cycle_progress = CycleProgressOut(**cp)
            rules = await improvement_engine.get_active_rules(s.id)
            active_rules_count = len(rules)
        except Exception:
            pass

        out.append(StrategyOut(
            id=s.id,
            name=s.name,
            description=s.description,
            enabled=s.enabled,
            status_text=s.status_text or "",
            llm_budget_fraction=s.llm_budget_fraction,
            capital_usd=state.capital_usd if state else 0,
            peak_capital_usd=state.peak_capital_usd if state else 0,
            total_pnl=state.total_pnl if state else 0,
            positions_open=actual_open,
            trades_won=state.trades_won if state else 0,
            trades_lost=state.trades_lost if state else 0,
            win_rate=round(wr, 4),
            mode=state.mode if state else "UNKNOWN",
            last_trade_at=state.last_trade_at if state else None,
            improvement_cycle=cycle_progress,
            active_rules_count=active_rules_count,
        ))
    return out


@router.get("/strategies/{strategy_id}/trades", response_model=list[TradeOut])
async def get_strategy_trades(
    strategy_id: str,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Trades de una estrategia."""
    query = select(Trade).where(Trade.strategy_id == strategy_id)
    if status:
        query = query.where(Trade.status == status.upper())
    query = query.order_by(Trade.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    trades = result.scalars().all()
    return [
        TradeOut(
            id=t.id, symbol=t.symbol, direction=t.direction,
            size_usd=t.size_usd, entry_price=t.entry_price,
            exit_price=t.exit_price, pnl=t.pnl, fees=t.fees,
            status=t.status, kelly_fraction=t.kelly_fraction,
            is_simulation=t.is_simulation, created_at=t.created_at,
            closed_at=t.closed_at,
        )
        for t in trades
    ]


@router.get("/strategies/{strategy_id}/bitacora", response_model=list[BitacoraOut])
async def get_strategy_bitacora(
    strategy_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Bitacora (diario de trading) de una estrategia."""
    result = await session.execute(
        select(Bitacora)
        .where(Bitacora.strategy_id == strategy_id)
        .order_by(Bitacora.created_at.desc())
        .limit(limit)
    )
    entries = result.scalars().all()
    return [
        BitacoraOut(
            id=b.id, trade_id=b.trade_id, strategy_id=b.strategy_id,
            symbol=b.symbol, direction=b.direction,
            entry_reasoning=b.entry_reasoning or "",
            market_context=b.market_context,
            entry_price=b.entry_price, entry_time=b.entry_time,
            exit_reason=b.exit_reason, exit_price=b.exit_price,
            exit_time=b.exit_time, pnl=b.pnl,
            hold_duration_minutes=b.hold_duration_minutes,
            lesson=b.lesson, created_at=b.created_at,
        )
        for b in entries
    ]


@router.get("/strategies/{strategy_id}/reports", response_model=list[LearningReportOut])
async def get_strategy_reports(
    strategy_id: str,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Reportes de aprendizaje de una estrategia."""
    result = await session.execute(
        select(LearningReport)
        .where(LearningReport.strategy_id == strategy_id)
        .order_by(LearningReport.created_at.desc())
        .limit(limit)
    )
    reports = result.scalars().all()
    return [
        LearningReportOut(
            id=r.id, strategy_id=r.strategy_id,
            report_number=r.report_number,
            trades_analyzed=r.trades_analyzed,
            analysis=r.analysis or "",
            patterns_found=r.patterns_found,
            recommendations=r.recommendations,
            stats_snapshot=r.stats_snapshot,
            created_at=r.created_at,
        )
        for r in reports
    ]


@router.get("/strategies/{strategy_id}/performance", response_model=PerformanceResponse)
async def get_strategy_performance(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Metricas de rendimiento de una estrategia."""
    analyzer = PerformanceAnalyzer(session, strategy_id=strategy_id)
    report = await analyzer.get_full_report()

    if not report:
        total = await analyzer.get_outcomes_count()
        return PerformanceResponse(
            total_trades=total, win_rate=0, profit_factor=0,
            sortino_ratio=0, expectancy=0,
            best_symbols=[], worst_symbols=[], calibration=[],
            buy_stats=None, sell_stats=None,
            best_hours=[], worst_hours=[],
            model_comparison=[], recommendations=[
                f"Datos insuficientes: {total}/30 trades cerrados",
            ],
            data_sufficient=False,
        )

    return PerformanceResponse(
        total_trades=report.total_trades,
        win_rate=report.win_rate,
        profit_factor=report.profit_factor,
        sortino_ratio=report.sortino_ratio,
        expectancy=report.expectancy,
        best_symbols=[
            SymbolPerformanceOut(
                symbol=s.symbol, total_trades=s.total_trades,
                wins=s.wins, losses=s.losses, win_rate=s.win_rate,
                total_pnl=round(s.total_pnl, 4), avg_pnl=round(s.avg_pnl, 4),
                profit_factor=round(s.profit_factor, 2),
                avg_hold_minutes=round(s.avg_hold_minutes, 1),
            )
            for s in report.best_symbols
        ],
        worst_symbols=[
            SymbolPerformanceOut(
                symbol=s.symbol, total_trades=s.total_trades,
                wins=s.wins, losses=s.losses, win_rate=s.win_rate,
                total_pnl=round(s.total_pnl, 4), avg_pnl=round(s.avg_pnl, 4),
                profit_factor=round(s.profit_factor, 2),
                avg_hold_minutes=round(s.avg_hold_minutes, 1),
            )
            for s in report.worst_symbols
        ],
        calibration=[
            CalibrationBucketOut(
                confidence_range=c.confidence_range,
                predicted_win_rate=round(c.predicted_win_rate, 3),
                actual_win_rate=round(c.actual_win_rate, 3),
                trade_count=c.trade_count,
                calibration_error=round(c.calibration_error, 3),
            )
            for c in report.calibration
        ],
        buy_stats=DirectionStatsOut(
            direction=report.buy_stats.direction,
            total_trades=report.buy_stats.total_trades,
            wins=report.buy_stats.wins, losses=report.buy_stats.losses,
            win_rate=report.buy_stats.win_rate,
            total_pnl=round(report.buy_stats.total_pnl, 4),
            avg_pnl=round(report.buy_stats.avg_pnl, 4),
            profit_factor=round(report.buy_stats.profit_factor, 2),
        ) if report.buy_stats else None,
        sell_stats=DirectionStatsOut(
            direction=report.sell_stats.direction,
            total_trades=report.sell_stats.total_trades,
            wins=report.sell_stats.wins, losses=report.sell_stats.losses,
            win_rate=report.sell_stats.win_rate,
            total_pnl=round(report.sell_stats.total_pnl, 4),
            avg_pnl=round(report.sell_stats.avg_pnl, 4),
            profit_factor=round(report.sell_stats.profit_factor, 2),
        ) if report.sell_stats else None,
        best_hours=report.best_hours,
        worst_hours=report.worst_hours,
        model_comparison=[
            ModelComparisonOut(
                model=m.model, total_trades=m.total_trades,
                wins=m.wins, win_rate=m.win_rate,
                total_pnl=round(m.total_pnl, 4),
                avg_pnl=round(m.avg_pnl, 4),
                profit_factor=round(m.profit_factor, 2),
            )
            for m in report.model_comparison
        ],
        recommendations=report.recommendations,
    )


# --- Improvement System Endpoints ---


@router.get("/strategies/{strategy_id}/improvement-cycles", response_model=list[ImprovementCycleOut])
async def get_improvement_cycles(
    strategy_id: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Historial de ciclos de mejora de una estrategia."""
    result = await session.execute(
        select(ImprovementCycle)
        .where(ImprovementCycle.strategy_id == strategy_id)
        .order_by(ImprovementCycle.started_at.desc())
        .limit(limit)
    )
    cycles = result.scalars().all()
    return [
        ImprovementCycleOut(
            id=c.id, strategy_id=c.strategy_id,
            cycle_number=c.cycle_number, trades_in_cycle=c.trades_in_cycle,
            status=c.status, loss_pattern_identified=c.loss_pattern_identified,
            rule_created_id=c.rule_created_id, started_at=c.started_at,
            completed_at=c.completed_at,
        )
        for c in cycles
    ]


@router.get("/strategies/{strategy_id}/improvement-rules", response_model=list[ImprovementRuleOut])
async def get_improvement_rules(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Reglas de mejora permanentes de una estrategia."""
    engine = ImprovementEngine(session)
    rules = await engine.get_active_rules(strategy_id)
    return [
        ImprovementRuleOut(
            id=r.id, strategy_id=r.strategy_id,
            cycle_number=r.cycle_number, rule_type=r.rule_type,
            description=r.description, pattern_name=r.pattern_name,
            condition_json=r.condition_json, trades_before_rule=r.trades_before_rule,
            win_rate_before=r.win_rate_before, is_active=r.is_active,
            created_at=r.created_at,
        )
        for r in rules
    ]


# ── Broker ─────────────────────────────────────────────────

async def _get_broker() -> BrokerInterface:
    """Crea instancia del broker según la configuración."""
    provider = settings.broker_provider.lower()
    if provider == 'capital':
        from app.broker.capital import CapitalBroker
        return CapitalBroker(
            api_key=settings.capital_api_key,
            identifier=settings.capital_identifier,
            password=settings.capital_password,
            environment=settings.capital_environment,
        )
    else:
        from app.broker.oanda import OANDABroker
        return OANDABroker(
            account_id=settings.oanda_account_id,
            access_token=settings.oanda_access_token,
            environment=settings.oanda_environment,
        )


@router.get("/broker/account", response_model=BrokerAccountOut)
async def get_broker_account(
    _user: str = Depends(verify_token),
):
    """Estado de la cuenta en OANDA (balance, equity, margen)."""
    broker = await _get_broker()
    try:
        connected = await broker.is_connected()
        if not connected:
            return BrokerAccountOut(
                balance=0, unrealized_pnl=0, margin_used=0,
                margin_available=0, equity=0, open_trades=0, connected=False,
            )
        account = await broker.get_account()
        positions = await broker.get_positions()
        return BrokerAccountOut(
            balance=account.balance,
            unrealized_pnl=account.unrealized_pnl,
            margin_used=account.margin_used,
            margin_available=account.margin_available,
            equity=account.equity,
            open_trades=len(positions),
            connected=True,
        )
    finally:
        await broker.close()


@router.get("/broker/positions", response_model=list[BrokerPositionOut])
async def get_broker_positions(
    _user: str = Depends(verify_token),
):
    """Posiciones abiertas en OANDA."""
    broker = await _get_broker()
    try:
        positions = await broker.get_positions()
        result = []
        for p in positions:
            # Obtener precio actual para calcular P&L no realizado
            try:
                price = await broker.get_price(p.instrument)
                current = price.mid
            except Exception:
                current = p.entry_price

            direction = "BUY" if p.units > 0 else "SELL"
            pnl = (current - p.entry_price) * p.units

            result.append(BrokerPositionOut(
                trade_id=p.trade_id,
                instrument=p.instrument,
                units=abs(p.units),
                direction=direction,
                entry_price=p.entry_price,
                current_price=current,
                unrealized_pnl=round(pnl, 2),
                stop_loss=p.stop_loss,
                take_profit=p.take_profit,
            ))
        return result
    finally:
        await broker.close()


@router.get("/broker/sync-status", response_model=BrokerSyncStatusOut)
async def get_broker_sync_status(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Comparación estado local vs broker."""
    # Trades abiertos locales
    result = await session.execute(
        select(func.count(Trade.id)).where(Trade.status == "OPEN")
    )
    local_open = result.scalar() or 0

    # Trades abiertos en broker
    broker = await _get_broker()
    try:
        broker_positions = await broker.get_positions()
        broker_open = len(broker_positions)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Error obteniendo posiciones del broker en sync-status"
        )
        broker_open = 0
    finally:
        await broker.close()

    # Últimas discrepancias del log
    result = await session.execute(
        select(BrokerSyncLog)
        .where(BrokerSyncLog.discrepancy.is_(True))
        .order_by(BrokerSyncLog.synced_at.desc())
        .limit(10)
    )
    disc_logs = result.scalars().all()
    discrepancies = [
        {
            "sync_type": d.sync_type,
            "local_value": d.local_value,
            "broker_value": d.broker_value,
            "synced_at": d.synced_at.isoformat() if d.synced_at else None,
        }
        for d in disc_logs
    ]

    # Último sync
    result = await session.execute(
        select(BrokerSyncLog.synced_at)
        .order_by(BrokerSyncLog.synced_at.desc())
        .limit(1)
    )
    last_sync = result.scalar()

    return BrokerSyncStatusOut(
        last_sync_at=last_sync,
        local_open_trades=local_open,
        broker_open_trades=broker_open,
        discrepancies=discrepancies,
        is_synced=local_open == broker_open and len(discrepancies) == 0,
    )


@router.post("/broker/sync", response_model=SyncResultOut)
async def force_broker_sync(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(verify_token),
):
    """Forzar reconciliación local vs broker."""
    broker = await _get_broker()
    try:
        broker_positions = await broker.get_positions()
    except Exception as e:
        return SyncResultOut(
            success=False, message=f"Error conectando al broker: {e}",
            trades_synced=0, discrepancies_found=0,
        )
    finally:
        await broker.close()

    # Trades abiertos locales con broker_trade_id
    result = await session.execute(
        select(Trade).where(Trade.status == "OPEN", Trade.broker_trade_id.isnot(None))
    )
    local_trades = {t.broker_trade_id: t for t in result.scalars().all()}

    broker_ids = {p.trade_id for p in broker_positions}
    discrepancies = 0

    # Trades locales que ya no existen en broker (cerrados externamente)
    for btid, trade in local_trades.items():
        if btid not in broker_ids:
            discrepancies += 1
            sync_log = BrokerSyncLog(
                sync_type="trade_closed_externally",
                local_value=f"Trade {trade.id} (OPEN)",
                broker_value=f"Trade {btid} not found",
                discrepancy=True,
            )
            session.add(sync_log)

    # Trades en broker que no tenemos localmente — ADOPTARLOS
    trades_adopted = 0
    for p in broker_positions:
        if p.trade_id not in local_trades:
            # Verificar que no exista ya por broker_trade_id
            existing = await session.execute(
                select(Trade).where(Trade.broker_trade_id == p.trade_id)
            )
            if existing.scalar_one_or_none():
                continue  # Ya existe, skip

            # Crear Trade local
            strategy_id = (
                "s1_pullback_20_up" if p.direction == "LONG"
                else "s2_pullback_20_down"
            )
            direction_db = "BUY" if p.direction == "LONG" else "SELL"
            size_usd = abs(p.units) * p.entry_price

            new_trade = Trade(
                strategy_id=strategy_id,
                market_id=f"capital:{p.instrument}",
                symbol=p.instrument,
                instrument=p.instrument,
                direction=direction_db,
                size_usd=size_usd,
                quantity=abs(p.units),
                entry_price=p.entry_price,
                stop_loss_price=p.stop_loss,
                initial_stop_price=p.stop_loss,
                take_profit_price=p.take_profit,
                original_size_usd=size_usd,
                broker_trade_id=p.trade_id,
                status="OPEN",
                is_simulation=False,
                pattern_name="adopted_from_broker",
            )
            session.add(new_trade)
            await session.flush()

            # Actualizar AgentState
            state_result = await session.execute(
                select(AgentState).where(AgentState.strategy_id == strategy_id)
            )
            state = state_result.scalar_one_or_none()
            if state:
                state.positions_open += 1
                state.trades_executed_total += 1
                state.last_trade_at = datetime.now(timezone.utc)

            trades_adopted += 1
            discrepancies += 1
            sync_log = BrokerSyncLog(
                sync_type="trade_adopted",
                local_value=f"Created Trade {new_trade.id} ({strategy_id})",
                broker_value=f"Deal {p.trade_id} ({p.instrument})",
                discrepancy=True,
            )
            session.add(sync_log)

    # Log de sync exitoso
    sync_log = BrokerSyncLog(
        sync_type="manual_sync",
        local_value=str(len(local_trades)),
        broker_value=str(len(broker_positions)),
        discrepancy=discrepancies > 0,
    )
    session.add(sync_log)
    await session.commit()

    return SyncResultOut(
        success=True,
        message=f"Sync completado. {discrepancies} discrepancias encontradas.",
        trades_synced=len(broker_positions),
        discrepancies_found=discrepancies,
    )


# ── Market State ───────────────────────────────────────────

@router.get("/market-state", response_model=AllMarketStatesOut)
async def get_all_market_states(
    _user: str = Depends(verify_token),
):
    """Estado del mercado para todos los instrumentos configurados."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    market_open = is_forex_market_open(now)
    session_name = get_current_session(now)

    instruments_data = []
    if market_open:
        broker = await _get_broker()
        analyzer = MarketStateAnalyzer()
        filter_engine = ContextFilterEngine()

        try:
            for instrument in settings.instruments_list:
                try:
                    candles = await broker.get_candles(instrument, "H1", 250)
                    if len(candles) < 200:
                        continue

                    state = analyzer.analyze(instrument, "H1", candles)
                    if not state:
                        continue

                    # Evaluar filtros para ambas direcciones
                    filters_long = []
                    filters_short = []

                    long_result = filter_engine.check_all_filters(state, state, "LONG")
                    for f in long_result.passed_filters:
                        filters_long.append(FilterStatusOut(name=f, passed=True))
                    for f in long_result.failed_filters:
                        filters_long.append(FilterStatusOut(name=f, passed=False))

                    short_result = filter_engine.check_all_filters(state, state, "SHORT")
                    for f in short_result.passed_filters:
                        filters_short.append(FilterStatusOut(name=f, passed=True))
                    for f in short_result.failed_filters:
                        filters_short.append(FilterStatusOut(name=f, passed=False))

                    instruments_data.append(MarketStateOut(
                        instrument=instrument,
                        timeframe="H1",
                        timestamp=state.timestamp,
                        price=state.price,
                        sma200=round(state.sma200, 5),
                        ema20=round(state.ema20, 5),
                        atr14=round(state.atr14, 5),
                        trend_state=state.trend_state,
                        price_vs_sma200=state.price_vs_sma200,
                        sma200_slope=state.sma200_slope,
                        ema20_slope=state.ema20_slope,
                        ma_state=state.ma_state,
                        ema20_vs_sma200=state.ema20_vs_sma200,
                        trap_zone=state.trap_zone,
                        last_swing_high=state.last_swing_high,
                        last_swing_low=state.last_swing_low,
                        impulse_range=round(state.impulse_range, 5),
                        filters_long=filters_long,
                        filters_short=filters_short,
                    ))
                except Exception:
                    continue
        finally:
            await broker.close()

    return AllMarketStatesOut(
        session_active=is_trading_session(now),
        current_session=session_name,
        market_open=market_open,
        instruments=instruments_data,
    )


@router.get("/market-state/{instrument}", response_model=MarketStateOut)
async def get_market_state(
    instrument: str,
    _user: str = Depends(verify_token),
):
    """Estado del mercado detallado para un instrumento específico."""
    from fastapi import HTTPException

    if instrument not in settings.instruments_list:
        raise HTTPException(status_code=404, detail=f"Instrumento {instrument} no configurado")

    broker = await _get_broker()
    analyzer = MarketStateAnalyzer()
    filter_engine = ContextFilterEngine()

    try:
        candles = await broker.get_candles(instrument, "H1", 250)
        if len(candles) < 200:
            raise HTTPException(
                status_code=503,
                detail=f"Datos insuficientes para {instrument}: {len(candles)} velas (necesita 200)",
            )

        state = analyzer.analyze(instrument, "H1", candles)
        if not state:
            raise HTTPException(status_code=503, detail=f"No se pudo analizar {instrument}")

        filters_long = []
        filters_short = []

        long_result = filter_engine.check_all_filters(state, state, "LONG")
        for f in long_result.passed_filters:
            filters_long.append(FilterStatusOut(name=f, passed=True))
        for f in long_result.failed_filters:
            filters_long.append(FilterStatusOut(name=f, passed=False))

        short_result = filter_engine.check_all_filters(state, state, "SHORT")
        for f in short_result.passed_filters:
            filters_short.append(FilterStatusOut(name=f, passed=True))
        for f in short_result.failed_filters:
            filters_short.append(FilterStatusOut(name=f, passed=False))

        return MarketStateOut(
            instrument=instrument,
            timeframe="H1",
            timestamp=state.timestamp,
            price=state.price,
            sma200=round(state.sma200, 5),
            ema20=round(state.ema20, 5),
            atr14=round(state.atr14, 5),
            trend_state=state.trend_state,
            price_vs_sma200=state.price_vs_sma200,
            sma200_slope=state.sma200_slope,
            ema20_slope=state.ema20_slope,
            ma_state=state.ma_state,
            ema20_vs_sma200=state.ema20_vs_sma200,
            trap_zone=state.trap_zone,
            last_swing_high=state.last_swing_high,
            last_swing_low=state.last_swing_low,
            impulse_range=round(state.impulse_range, 5),
            filters_long=filters_long,
            filters_short=filters_short,
        )
    finally:
        await broker.close()


# ── Trade Chart Data ─────────────────────────────────────


@router.get("/trades/{trade_id}/chart-data", response_model=TradeChartDataOut)
async def get_trade_chart_data(
    trade_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Retorna velas OHLCV + marcadores para graficar un trade."""
    import logging

    log = logging.getLogger(__name__)

    result = await session.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Trade no encontrado")

    instrument = trade.instrument or trade.symbol.replace("/", "_")
    timeframe = trade.timeframe_entry or "M5"

    # Rango de tiempo: 1h antes de la entrada hasta 1h después del cierre (o ahora)
    entry_dt = trade.created_at
    if trade.closed_at:
        end_dt = trade.closed_at + timedelta(hours=1)
    else:
        end_dt = datetime.now(timezone.utc)
    start_dt = entry_dt - timedelta(hours=1)

    # Calcular cuántas velas necesitamos según timeframe
    tf_minutes = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240}
    mins = tf_minutes.get(timeframe, 5)
    total_minutes = (end_dt - start_dt).total_seconds() / 60
    count = min(int(total_minutes / mins) + 20, 500)

    candles = []
    try:
        broker_chart = await _get_broker()
        candles_raw = await broker_chart.get_candles(
            instrument, timeframe, count=count, from_dt=start_dt, to_dt=end_dt
        )
        await broker_chart.close()

        candles = [
            ChartCandleOut(
                time=int(c.timestamp.timestamp()),
                open=round(c.open, 5),
                high=round(c.high, 5),
                low=round(c.low, 5),
                close=round(c.close, 5),
                volume=c.volume,
            )
            for c in candles_raw
        ]
    except Exception as e:
        log.exception("Error obteniendo velas para chart: %s", e)

    # Marcadores de entrada y salida
    markers = []
    entry_ts = int(entry_dt.timestamp())

    if trade.direction == "BUY":
        markers.append(
            TradeMarkerOut(
                time=entry_ts,
                position="belowBar",
                color="#22c55e",
                shape="arrowUp",
                text=f"BUY @ {trade.entry_price:.5f}",
            )
        )
    else:
        markers.append(
            TradeMarkerOut(
                time=entry_ts,
                position="aboveBar",
                color="#ef4444",
                shape="arrowDown",
                text=f"SELL @ {trade.entry_price:.5f}",
            )
        )

    if trade.closed_at and trade.exit_price:
        exit_ts = int(trade.closed_at.timestamp())
        is_win = trade.pnl and trade.pnl > 0
        markers.append(
            TradeMarkerOut(
                time=exit_ts,
                position="aboveBar" if trade.direction == "BUY" else "belowBar",
                color="#22c55e" if is_win else "#ef4444",
                shape="circle",
                text=f"EXIT @ {trade.exit_price:.5f}" + (f" ({trade.exit_reason})" if trade.exit_reason else ""),
            )
        )

    # Líneas de precio (entry, SL, TP)
    price_lines = [
        TradePriceLine(
            price=trade.entry_price,
            color="#3b82f6",
            line_style=2,
            label="Entrada",
        )
    ]
    if trade.stop_loss_price:
        price_lines.append(
            TradePriceLine(
                price=trade.stop_loss_price,
                color="#ef4444",
                line_style=1,
                label="Stop Loss",
            )
        )
    if trade.take_profit_price:
        price_lines.append(
            TradePriceLine(
                price=trade.take_profit_price,
                color="#22c55e",
                line_style=1,
                label="Take Profit",
            )
        )
    if trade.exit_price:
        price_lines.append(
            TradePriceLine(
                price=trade.exit_price,
                color="#f59e0b",
                line_style=0,
                label="Salida",
            )
        )

    return TradeChartDataOut(
        trade_id=trade.id,
        symbol=trade.symbol,
        direction=trade.direction,
        timeframe=timeframe,
        status=trade.status,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        stop_loss=trade.stop_loss_price,
        take_profit=trade.take_profit_price,
        pnl=trade.pnl,
        pattern_name=trade.pattern_name,
        entry_time=entry_dt.isoformat() if entry_dt else None,
        exit_time=trade.closed_at.isoformat() if trade.closed_at else None,
        candles=candles,
        markers=markers,
        price_lines=price_lines,
    )
