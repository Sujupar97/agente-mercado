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
    BitacoraOut,
    CalibrationBucketOut,
    ConfigUpdate,
    CycleProgressOut,
    CycleResponse,
    DailyPnL,
    DirectionStatsOut,
    HealthResponse,
    ImprovementCycleOut,
    ImprovementRuleOut,
    LearningLogOut,
    LearningReportOut,
    LLMUsageResponse,
    ModelComparisonOut,
    PerformanceResponse,
    PnLHistoryResponse,
    PositionOut,
    SignalOut,
    StrategyOut,
    SymbolPerformanceOut,
    TradeOut,
)
from app.config import settings
from app.core.state import StateManager
from app.db.database import get_session
from app.db.models import AgentState, Bitacora, CostLog, ImprovementCycle, ImprovementRule, LearningLog, LearningReport, Signal, Strategy, Trade
from app.learning.adaptive import AdaptiveFilter
from app.learning.improvement_engine import ImprovementEngine
from app.learning.performance import PerformanceAnalyzer
from app.llm.budget import LLMBudget
from app.pnl.calculator import PnLCalculator

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
    state_mgr = StateManager(session)
    state = await state_mgr.ensure_state()
    pnl_calc = PnLCalculator(session)
    budget = LLMBudget()
    summary = await pnl_calc.get_summary()
    llm_usage = await budget.get_usage()
    await budget.close()

    # Calcular capital invertido en posiciones abiertas
    positions_result = await session.execute(
        select(func.coalesce(func.sum(Trade.size_usd), 0.0))
        .where(Trade.status == "OPEN")
    )
    capital_in_positions = float(positions_result.scalar() or 0.0)

    # Evaluar supervivencia "pay or die"
    survival_check = await state_mgr.evaluate_survival()

    return AgentStatus(
        mode=state.mode,
        capital_usd=state.capital_usd,
        initial_capital_usd=settings.initial_capital_usd,
        peak_capital_usd=state.peak_capital_usd,
        capital_in_positions=round(capital_in_positions, 2),
        total_pnl=summary["total_pnl"],
        total_costs=summary["total_costs"],
        net_profit=summary["net_profit"],
        net_7d=summary["net_7d"],
        net_14d=summary["net_14d"],
        win_rate=summary["win_rate"],
        drawdown_pct=summary["drawdown_pct"],
        positions_open=state.positions_open,
        trades_won=state.trades_won,
        trades_lost=state.trades_lost,
        markets_scanned_total=state.markets_scanned_total,
        trades_executed_total=state.trades_executed_total,
        last_cycle_at=state.last_cycle_at,
        cycle_interval_minutes=settings.cycle_interval_minutes,
        llm_usage=llm_usage,
        survival_status=survival_check.action,
        survival_reason=survival_check.reason if survival_check.action != "CONTINUE" else None,
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
            positions_open=state.positions_open if state else 0,
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
