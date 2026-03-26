"""Punto de entrada — FastAPI app con lifespan para scheduler y conexiones."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.scheduler import start_scheduler, stop_scheduler
from app.db.database import engine, Base, async_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agente-mercado")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown del agente."""
    log.info("=== Agente de Mercado iniciando ===")
    log.info("Modo: %s | Capital: $%.2f", settings.agent_mode, settings.initial_capital_usd)

    # Importar modelos y crear tablas si no existen
    from app.db import models  # noqa: F401
    from app.db.models import AgentState, Strategy
    from app.strategies.registry import STRATEGIES

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migrar columnas nuevas que create_all no agrega a tablas existentes
        from sqlalchemy import text
        migrations = [
            # Trade: 7 columnas técnicas de entrada (improvement engine)
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_ema20_distance_atr FLOAT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_sma200_distance_atr FLOAT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_candle_body_pct FLOAT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_candle_upper_wick_pct FLOAT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_candle_lower_wick_pct FLOAT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_atr14 FLOAT",
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_retrace_pct FLOAT",
            # AgentState: stepped compound interest
            "ALTER TABLE agent_state ADD COLUMN IF NOT EXISTS base_capital_usd FLOAT",
            "ALTER TABLE agent_state ADD COLUMN IF NOT EXISTS next_threshold_usd FLOAT",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # Columna ya existe o DB no soporta IF NOT EXISTS

        # Bitácora retroactiva (mismo conn)
        try:
            r = await conn.execute(text("""
                UPDATE bitacora SET
                    exit_reason = t.exit_reason, exit_price = t.exit_price,
                    exit_time = t.closed_at, pnl = t.pnl,
                    hold_duration_minutes = EXTRACT(EPOCH FROM (t.closed_at - bitacora.entry_time)) / 60
                FROM trades t
                WHERE bitacora.trade_id = t.id AND t.status = 'CLOSED' AND bitacora.pnl IS NULL
            """))
            if r.rowcount > 0:
                log.info("Bitácora: %d entries actualizadas", r.rowcount)
        except Exception:
            log.exception("Error Bitácora migration")

        # Sembrar estrategias nuevas (mismo conn)
        for sid, config in STRATEGIES.items():
            try:
                r = await conn.execute(text("SELECT id FROM strategies WHERE id = :sid"), {"sid": sid})
                if r.first() is None:
                    log.info("Sembrando estrategia: %s", sid)
                    await conn.execute(text(
                        "INSERT INTO strategies (id, name, description, enabled, params, status_text, llm_budget_fraction) "
                        "VALUES (:id, :name, :desc, true, :params, :status, :budget)"
                    ), {"id": sid, "name": config.name, "desc": config.description,
                        "params": '{"signal_type": "' + config.signal_type + '"}',
                        "status": "Activa — esperando señales", "budget": config.llm_budget_fraction})
                    await conn.execute(text(
                        "INSERT INTO agent_state (strategy_id, mode, capital_usd, peak_capital_usd) "
                        "VALUES (:sid, 'SIMULATION', :cap, :cap)"
                    ), {"sid": sid, "cap": config.initial_capital_usd})
                    log.info("  OK: %s", sid)
            except Exception:
                log.exception("Error sembrando %s", sid)

    log.info("Tablas verificadas/creadas")

    # Legacy seeding (DB vacía — primera ejecución)
    async with async_session_factory() as session:
        from sqlalchemy import select, func
        result = await session.execute(select(func.count(Strategy.id)))
        existing_count = result.scalar() or 0
        if existing_count == 0:
            log.info("DB vacía — sembrando estrategias...")
            for sid, config in STRATEGIES.items():
                session.add(Strategy(
                    id=config.id, name=config.name,
                    description=config.description, enabled=config.enabled,
                    params={"signal_type": config.signal_type, "direction": config.direction,
                            "instruments": list(config.instruments),
                            "primary_timeframe": config.primary_timeframe,
                            "context_timeframe": config.context_timeframe,
                            "risk_per_trade_pct": config.risk_per_trade_pct,
                            "min_risk_reward": config.min_risk_reward,
                            "max_concurrent_positions": config.max_concurrent_positions,
                            "cycle_interval_minutes": config.cycle_interval_minutes,
                            "trades_per_improvement_cycle": config.trades_per_improvement_cycle},
                    status_text="Activa — esperando señales",
                    llm_budget_fraction=config.llm_budget_fraction,
                ))
                session.add(AgentState(
                    strategy_id=config.id, mode="SIMULATION",
                    capital_usd=config.initial_capital_usd,
                    peak_capital_usd=config.initial_capital_usd,
                ))
                log.info("  Sembrada: %s", config.id)
            await session.commit()
        else:
            # DB ya tiene estrategias — verificar si hay nuevas en STRATEGIES
            log.info("DB tiene %d estrategias, STRATEGIES tiene %d — verificando nuevas...",
                     existing_count, len(STRATEGIES))
            for sid, config in STRATEGIES.items():
                try:
                    existing = await session.execute(select(Strategy).where(Strategy.id == sid))
                    if existing.scalar_one_or_none() is None:
                        log.info("Nueva estrategia detectada: %s — sembrando...", sid)
                        session.add(Strategy(
                            id=config.id, name=config.name,
                            description=config.description, enabled=config.enabled,
                            params={"signal_type": config.signal_type, "direction": config.direction,
                                    "instruments": list(config.instruments),
                                    "primary_timeframe": config.primary_timeframe,
                                    "context_timeframe": config.context_timeframe,
                                    "risk_per_trade_pct": config.risk_per_trade_pct,
                                    "min_risk_reward": config.min_risk_reward,
                                    "max_concurrent_positions": config.max_concurrent_positions,
                                    "cycle_interval_minutes": config.cycle_interval_minutes,
                                    "trades_per_improvement_cycle": config.trades_per_improvement_cycle},
                            status_text="Activa — esperando señales",
                            llm_budget_fraction=config.llm_budget_fraction,
                        ))
                        session.add(AgentState(
                            strategy_id=config.id, mode="SIMULATION",
                            capital_usd=config.initial_capital_usd,
                            peak_capital_usd=config.initial_capital_usd,
                        ))
                        await session.flush()
                        log.info("  Sembrada: %s", config.id)
                except Exception:
                    log.exception("Error sembrando estrategia %s", sid)
            await session.commit()

    # Iniciar scheduler
    await start_scheduler()
    log.info("Scheduler iniciado (ciclo cada %d minutos)", settings.cycle_interval_minutes)

    yield

    # Shutdown
    log.info("=== Agente de Mercado deteniendo ===")
    await stop_scheduler()
    await engine.dispose()
    log.info("Recursos liberados. Adiós.")


app = FastAPI(
    title="Agente de Mercado",
    description="Agente autónomo de trading cuantitativo con IA",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — permitir cualquier origen (API protegida por JWT)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rutas
from app.api.routes import router  # noqa: E402

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "agent": "Agente de Mercado v0.1.0"}
