"""Script para crear estado inicial del agente en la base de datos."""

import asyncio

from sqlalchemy import select

from app.config import settings
from app.db.database import async_session_factory, engine, Base
from app.db.models import AgentState


async def seed():
    # Crear tablas si no existen
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Verificar si ya existe estado
        result = await session.execute(select(AgentState).where(AgentState.id == 1))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Estado existente: modo={existing.mode}, capital=${existing.capital_usd:.2f}")
            return

        # Crear estado inicial
        state = AgentState(
            id=1,
            mode=settings.agent_mode,
            capital_usd=settings.initial_capital_usd,
            peak_capital_usd=settings.initial_capital_usd,
        )
        session.add(state)
        await session.commit()
        print(f"Estado inicial creado: modo={state.mode}, capital=${state.capital_usd:.2f}")


if __name__ == "__main__":
    asyncio.run(seed())
