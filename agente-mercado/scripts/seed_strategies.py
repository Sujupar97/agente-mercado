"""Script para recrear tablas y sembrar datos iniciales de las estrategias Oliver Vélez."""

import asyncio
import sys
from pathlib import Path

# Asegurar que el path del proyecto esta en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine, Base
from app.db import models  # noqa: F401 — importa todos los modelos para que Base los conozca
from app.db.database import async_session_factory
from app.db.models import AgentState, Strategy
from app.strategies.registry import STRATEGIES


async def main():
    print("=== Semilla de Estrategias Oliver Vélez ===\n")

    # 1. Recrear TODAS las tablas (drop + create)
    print("1. Recreando tablas...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("   Tablas recreadas exitosamente.\n")

    # 2. Insertar estrategias + AgentStates
    print("2. Insertando estrategias y estados iniciales...")
    async with async_session_factory() as session:
        for sid, config in STRATEGIES.items():
            # Strategy
            strategy = Strategy(
                id=config.id,
                name=config.name,
                description=config.description,
                enabled=config.enabled,
                params={
                    "signal_type": config.signal_type,
                    "detection_timeframes": config.detection_timeframes,
                    "trend_timeframe": config.trend_timeframe,
                    "tp_min": config.tp_min,
                    "tp_max": config.tp_max,
                    "sl_min": config.sl_min,
                    "sl_max": config.sl_max,
                    "max_per_trade_pct": config.max_per_trade_pct,
                    "min_confidence": config.min_confidence,
                    "max_concurrent_positions": config.max_concurrent_positions,
                    "cycle_interval_minutes": config.cycle_interval_minutes,
                    "trades_per_improvement_cycle": config.trades_per_improvement_cycle,
                },
                status_text="Iniciando..." if config.enabled else "Placeholder — pendiente de configuración",
                llm_budget_fraction=config.llm_budget_fraction,
            )
            session.add(strategy)

            # AgentState
            state = AgentState(
                strategy_id=config.id,
                mode="SIMULATION" if config.enabled else "PAUSED",
                capital_usd=config.initial_capital_usd,
                peak_capital_usd=config.initial_capital_usd,
            )
            session.add(state)

            status = "ACTIVA" if config.enabled else "DESHABILITADA"
            print(f"   [{config.id}] {config.name} — ${config.initial_capital_usd} — {status}")

        await session.commit()

    print("\n3. Verificando...")
    async with async_session_factory() as session:
        from sqlalchemy import select, func

        # Verificar strategies
        result = await session.execute(select(func.count(Strategy.id)))
        strat_count = result.scalar()
        print(f"   Estrategias: {strat_count}")

        # Verificar agent states
        result = await session.execute(select(func.count(AgentState.id)))
        state_count = result.scalar()
        print(f"   Agent States: {state_count}")

        # Listar cada una
        result = await session.execute(
            select(Strategy.id, Strategy.name, Strategy.enabled)
        )
        for row in result.all():
            status = "activa" if row[2] else "deshabilitada"
            print(f"   - {row[0]}: {row[1]} ({status})")

    print("\n=== Semilla completada exitosamente ===")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
