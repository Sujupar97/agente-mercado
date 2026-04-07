"""Scheduler Forex — APScheduler para el orquestador + sync de posiciones."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_orchestrator = None
_broker = None


def _get_broker():
    """Crea el broker singleton según la configuración."""
    global _broker
    if _broker is not None:
        return _broker

    provider = settings.broker_provider.lower()

    if provider == "capital":
        from app.broker.capital import CapitalBroker
        if settings.capital_api_key and settings.capital_identifier:
            _broker = CapitalBroker(
                api_key=settings.capital_api_key,
                identifier=settings.capital_identifier,
                password=settings.capital_password,
                environment=settings.capital_environment,
            )
            log.info(
                "Broker Capital.com inicializado: env=%s",
                settings.capital_environment,
            )
        else:
            log.warning(
                "Capital.com no configurado (falta api_key o identifier) — "
                "el orquestador no podrá operar"
            )
    elif provider == "oanda":
        from app.broker.oanda import OANDABroker
        if settings.oanda_account_id and settings.oanda_access_token:
            _broker = OANDABroker(
                account_id=settings.oanda_account_id,
                access_token=settings.oanda_access_token,
                environment=settings.oanda_environment,
            )
            log.info(
                "Broker OANDA inicializado: env=%s",
                settings.oanda_environment,
            )
        else:
            log.warning(
                "OANDA no configurado (falta account_id o access_token) — "
                "el orquestador no podrá operar"
            )
    else:
        log.error("Broker provider desconocido: %s (usar 'capital' o 'oanda')", provider)

    return _broker


def _ensure_orchestrator():
    """Crea el orquestador singleton si aún no existe."""
    global _orchestrator
    broker = _get_broker()
    if broker is None:
        return None

    if _orchestrator is None:
        from app.core.orchestrator import ForexOrchestrator
        _orchestrator = ForexOrchestrator(broker)

    return _orchestrator


async def _run_context_cycle():
    """Fase 1: Analiza H1/H4, corre filtros, cachea instrumentos listos."""
    orch = _ensure_orchestrator()
    if orch is None:
        return
    try:
        await orch.run_context_cycle()
    except Exception:
        log.exception("Error en ciclo de contexto H1/H4")


async def _run_entry_cycle():
    """Fase 2: Busca entradas en M1 para instrumentos listos."""
    orch = _ensure_orchestrator()
    if orch is None:
        return
    try:
        await orch.run_entry_cycle()
    except Exception:
        log.exception("Error en ciclo de entrada M1")


async def _run_position_sync():
    """Sincroniza posiciones con el broker."""
    orch = _ensure_orchestrator()
    if orch is None:
        return

    try:
        from app.db.database import async_session_factory
        async with async_session_factory() as session:
            await orch._manage_positions(session)
            await session.commit()
    except Exception:
        log.exception("Error en sincronización de posiciones")


async def _run_broker_balance_sync():
    """Sincroniza el balance/equity del broker cada 5 min."""
    orch = _ensure_orchestrator()
    if orch is None:
        return
    try:
        await orch.sync_broker_account()
    except Exception:
        log.exception("Error en sync de broker balance")


async def start_scheduler() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()

    # Job 1: Contexto H1/H4 — cada 15 min
    _scheduler.add_job(
        _run_context_cycle,
        trigger=IntervalTrigger(minutes=15),
        id="context_cycle",
        name="Contexto H1/H4 (8 filtros)",
        replace_existing=True,
        max_instances=1,
    )

    # Job 2: Entradas M1 — cada 1 min
    _scheduler.add_job(
        _run_entry_cycle,
        trigger=IntervalTrigger(minutes=1),
        id="entry_cycle",
        name="Entradas M1 (pullback + patrón)",
        replace_existing=True,
        max_instances=1,
    )

    # Job 3: Sync de posiciones — cada 30 segundos
    _scheduler.add_job(
        _run_position_sync,
        trigger=IntervalTrigger(seconds=30),
        id="position_sync",
        name="Sincronización posiciones broker",
        replace_existing=True,
        max_instances=1,
    )

    # Job 4: Sync de balance broker — cada 5 min
    _scheduler.add_job(
        _run_broker_balance_sync,
        trigger=IntervalTrigger(minutes=5),
        id="broker_balance_sync",
        name="Sync balance broker (cada 5 min)",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    log.info(
        "Scheduler Forex iniciado: broker=%s | contexto=15min | entradas=1min | "
        "pos_sync=30seg | balance_sync=5min",
        settings.broker_provider,
    )


async def stop_scheduler() -> None:
    global _scheduler, _orchestrator, _broker
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler detenido")
    if _orchestrator:
        await _orchestrator.close()
        _orchestrator = None
    if _broker:
        await _broker.close()
        _broker = None


async def trigger_manual_cycle() -> None:
    """Fuerza un ciclo manual completo (contexto + entradas)."""
    await _run_context_cycle()
    await _run_entry_cycle()
