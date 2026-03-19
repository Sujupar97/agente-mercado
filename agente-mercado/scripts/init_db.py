"""Inicializa la DB: crea tablas si no existen y siembra estrategias si están vacías."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine, Base, async_session_factory
from app.db import models  # noqa: F401
from app.db.models import AgentState, Strategy
from app.strategies.registry import STRATEGIES


async def main():
    print("=== init_db: Inicializando base de datos ===")

    # 1. Crear tablas que NO existan (no hace drop)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("   Tablas verificadas/creadas.")

    # 2. Si no hay estrategias, sembrar
    async with async_session_factory() as session:
        from sqlalchemy import select, func

        result = await session.execute(select(func.count(Strategy.id)))
        count = result.scalar()

        if count == 0:
            print("   Sin estrategias — sembrando...")
            for sid, config in STRATEGIES.items():
                strategy = Strategy(
                    id=config.id,
                    name=config.name,
                    description=config.description,
                    enabled=config.enabled,
                    params={
                        "signal_type": config.signal_type,
                        "direction": config.direction,
                        "instruments": list(config.instruments),
                        "primary_timeframe": config.primary_timeframe,
                        "context_timeframe": config.context_timeframe,
                        "risk_per_trade_pct": config.risk_per_trade_pct,
                        "min_risk_reward": config.min_risk_reward,
                        "max_concurrent_positions": config.max_concurrent_positions,
                        "cycle_interval_minutes": config.cycle_interval_minutes,
                        "trades_per_improvement_cycle": config.trades_per_improvement_cycle,
                    },
                    status_text="Activa — esperando señales",
                    llm_budget_fraction=config.llm_budget_fraction,
                )
                session.add(strategy)

                state = AgentState(
                    strategy_id=config.id,
                    mode="SIMULATION",
                    capital_usd=config.initial_capital_usd,
                    peak_capital_usd=config.initial_capital_usd,
                )
                session.add(state)
                print(f"   [{config.id}] {config.name}")

            await session.commit()
            print("   Semilla completada.")
        else:
            print(f"   {count} estrategias existentes — sin cambios.")

    await engine.dispose()
    print("=== init_db: Listo ===")


if __name__ == "__main__":
    asyncio.run(main())
