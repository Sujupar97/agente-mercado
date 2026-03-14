"""Scheduler — APScheduler para el orquestador multi-estrategia + tracker."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_orchestrator = None


async def _run_orchestrator_cycle():
    """Ejecuta un ciclo del orquestador multi-estrategia."""
    global _orchestrator
    if _orchestrator is None:
        from app.core.orchestrator import StrategyOrchestrator
        _orchestrator = StrategyOrchestrator()

    try:
        await _orchestrator.run_cycle()
    except Exception:
        log.exception("Error en ciclo del orquestador")


async def _run_position_check():
    """Verifica posiciones abiertas contra precios actuales (GRATIS — solo API publica)."""
    from app.trading.tracker import PositionTracker

    try:
        await PositionTracker.run_independent_check()
    except Exception:
        log.exception("Error en chequeo rapido de posiciones")


async def start_scheduler() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()

    # Job 1: Ciclo multi-estrategia — cada 5 min (intervalo minimo de scalping)
    _scheduler.add_job(
        _run_orchestrator_cycle,
        trigger=IntervalTrigger(minutes=settings.cycle_interval_minutes),
        id="orchestrator_cycle",
        name="Ciclo multi-estrategia",
        replace_existing=True,
        max_instances=1,
    )

    # Job 2: Chequeo rapido de TP/SL — cada N segundos (GRATIS)
    _scheduler.add_job(
        _run_position_check,
        trigger=IntervalTrigger(seconds=settings.position_check_seconds),
        id="position_check",
        name="Chequeo rapido de posiciones TP/SL",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    log.info(
        "Scheduler iniciado: ciclo=%dmin, chequeo posiciones=%dseg",
        settings.cycle_interval_minutes,
        settings.position_check_seconds,
    )


async def stop_scheduler() -> None:
    global _scheduler, _orchestrator
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler detenido")
    if _orchestrator:
        await _orchestrator.close()
        _orchestrator = None


async def trigger_manual_cycle() -> None:
    """Fuerza un ciclo manual fuera del scheduler."""
    await _run_orchestrator_cycle()
