"""Punto de entrada — FastAPI app con lifespan para scheduler y conexiones."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.scheduler import start_scheduler, stop_scheduler
from app.db.database import engine

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

    # Importar modelos para que Alembic los conozca
    from app.db import models  # noqa: F401

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

# CORS — orígenes permitidos (local + producción via env var)
_cors_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5176",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5176",
    "http://localhost:3000",
]
# Agregar origen de producción (Netlify) si está configurado
_frontend_url = os.getenv("FRONTEND_URL", "")
if _frontend_url:
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rutas
from app.api.routes import router  # noqa: E402

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "agent": "Agente de Mercado v0.1.0"}
