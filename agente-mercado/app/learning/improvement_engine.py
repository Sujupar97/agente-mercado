"""Motor del ciclo de mejora de 20 trades.

Cada 20 trades cerrados por estrategia:
1. Analiza ganadores vs perdedores con LLM
2. Identifica el patrón #1 más recurrente en pérdidas
3. Crea una ImprovementRule PERMANENTE
4. La regla se aplica en los siguientes trades vía RuleBasedSignalGenerator

Las reglas son IRREVOCABLES — se acumulan con el tiempo.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Bitacora,
    ImprovementCycle,
    ImprovementRule,
    Trade,
)
from app.strategies.prompts import IMPROVEMENT_ANALYSIS_PROMPT
from app.strategies.registry import STRATEGIES

log = logging.getLogger(__name__)


class ImprovementEngine:
    """Gestiona el ciclo de mejora de 20 trades y reglas permanentes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_active_cycle(
        self, strategy_id: str,
    ) -> ImprovementCycle:
        """Obtiene el ciclo activo o crea uno nuevo."""
        result = await self._session.execute(
            select(ImprovementCycle)
            .where(
                ImprovementCycle.strategy_id == strategy_id,
                ImprovementCycle.status == "active",
            )
            .order_by(ImprovementCycle.started_at.desc())
            .limit(1)
        )
        cycle = result.scalar_one_or_none()

        if not cycle:
            # Determinar número de ciclo
            count_result = await self._session.execute(
                select(ImprovementCycle)
                .where(ImprovementCycle.strategy_id == strategy_id)
            )
            existing = count_result.scalars().all()
            cycle_number = len(existing) + 1

            cycle = ImprovementCycle(
                strategy_id=strategy_id,
                cycle_number=cycle_number,
                trades_in_cycle=0,
                status="active",
            )
            self._session.add(cycle)
            await self._session.flush()
            log.info(
                "[%s] Ciclo de mejora #%d creado",
                strategy_id, cycle_number,
            )

        return cycle

    async def record_trade(self, trade: Trade) -> bool:
        """Registra un trade cerrado en el ciclo activo.

        Returns:
            True si el ciclo alcanzó 20 trades y está listo para análisis.
        """
        strategy_id = trade.strategy_id
        config = STRATEGIES.get(strategy_id)
        threshold = config.trades_per_improvement_cycle if config else 20

        cycle = await self.get_or_create_active_cycle(strategy_id)
        cycle.trades_in_cycle += 1

        if cycle.trades_in_cycle >= threshold:
            cycle.status = "analyzing"
            log.info(
                "[%s] Ciclo #%d alcanzó %d trades — listo para análisis",
                strategy_id, cycle.cycle_number, cycle.trades_in_cycle,
            )
            return True

        return False

    async def analyze_cycle(self, strategy_id: str) -> ImprovementRule | None:
        """Analiza el ciclo completado y genera una regla permanente.

        1. Obtiene los trades del ciclo
        2. Separa ganadores vs perdedores
        3. Llama al LLM para identificar el patrón #1
        4. Crea ImprovementRule
        5. Persiste en CLAUDE.md
        """
        # Obtener ciclo en estado "analyzing"
        result = await self._session.execute(
            select(ImprovementCycle)
            .where(
                ImprovementCycle.strategy_id == strategy_id,
                ImprovementCycle.status == "analyzing",
            )
            .order_by(ImprovementCycle.started_at.desc())
            .limit(1)
        )
        cycle = result.scalar_one_or_none()
        if not cycle:
            return None

        config = STRATEGIES.get(strategy_id)
        if not config:
            return None

        # Obtener trades cerrados recientes (los del ciclo)
        trades_result = await self._session.execute(
            select(Trade)
            .where(
                Trade.strategy_id == strategy_id,
                Trade.status == "CLOSED",
            )
            .order_by(Trade.closed_at.desc())
            .limit(cycle.trades_in_cycle)
        )
        trades = list(trades_result.scalars().all())

        if not trades:
            cycle.status = "completed"
            cycle.completed_at = datetime.now(timezone.utc)
            return None

        # Separar ganadores y perdedores
        winners = [t for t in trades if t.pnl and t.pnl > 0]
        losers = [t for t in trades if t.pnl and t.pnl <= 0]

        if not losers:
            # Todos ganadores — no hay patrón de pérdida
            log.info("[%s] Ciclo #%d: 0 pérdidas, nada que mejorar", strategy_id, cycle.cycle_number)
            cycle.status = "completed"
            cycle.completed_at = datetime.now(timezone.utc)
            # Crear nuevo ciclo
            await self.get_or_create_active_cycle(strategy_id)
            return None

        # Obtener reglas existentes
        existing_rules = await self.get_active_rules(strategy_id)
        existing_rules_text = "\n".join(
            f"- [{r.pattern_name}] {r.description}" for r in existing_rules
        ) or "Ninguna"

        # Formatear trades
        winners_data = self._format_trades_for_prompt(winners)
        losers_data = self._format_trades_for_prompt(losers)

        # Llamar al LLM
        prompt = IMPROVEMENT_ANALYSIS_PROMPT.format(
            total_trades=len(trades),
            strategy_name=config.name,
            strategy_description=config.description,
            wins_count=len(winners),
            winners_data=winners_data,
            losses_count=len(losers),
            losers_data=losers_data,
            existing_rules=existing_rules_text,
        )

        try:
            resp = await self._call_llm_for_json(prompt)
            if not resp or not isinstance(resp, dict):
                log.warning("[%s] LLM no retornó análisis válido para ciclo", strategy_id)
                cycle.status = "completed"
                cycle.completed_at = datetime.now(timezone.utc)
                await self.get_or_create_active_cycle(strategy_id)
                return None

            # Crear regla permanente
            win_rate = len(winners) / len(trades) if trades else 0
            rule = ImprovementRule(
                strategy_id=strategy_id,
                cycle_number=cycle.cycle_number,
                rule_type=resp.get("rule_type", "condition_filter"),
                description=resp.get("description", "Regla generada por LLM"),
                pattern_name=resp.get("pattern_name", f"rule_cycle_{cycle.cycle_number}"),
                condition_json=resp.get("condition", {}),
                trades_before_rule=len(trades),
                win_rate_before=win_rate,
                is_active=True,
            )
            self._session.add(rule)
            await self._session.flush()

            # Actualizar ciclo
            cycle.loss_pattern_identified = resp.get("description", "")
            cycle.rule_created_id = rule.id
            cycle.status = "completed"
            cycle.completed_at = datetime.now(timezone.utc)

            log.info(
                "[%s] Ciclo #%d completado — Regla creada: '%s' (%s)",
                strategy_id, cycle.cycle_number,
                rule.pattern_name, rule.description,
            )

            # Persistir en CLAUDE.md
            self._persist_rule_to_claude_md(strategy_id, cycle.cycle_number, rule)

            # Crear nuevo ciclo
            await self.get_or_create_active_cycle(strategy_id)

            return rule

        except Exception:
            log.exception("[%s] Error analizando ciclo de mejora", strategy_id)
            cycle.status = "completed"
            cycle.completed_at = datetime.now(timezone.utc)
            await self.get_or_create_active_cycle(strategy_id)
            return None

    async def get_active_rules(self, strategy_id: str) -> list[ImprovementRule]:
        """Retorna TODAS las reglas activas de una estrategia."""
        result = await self._session.execute(
            select(ImprovementRule)
            .where(
                ImprovementRule.strategy_id == strategy_id,
                ImprovementRule.is_active.is_(True),
            )
            .order_by(ImprovementRule.created_at)
        )
        return list(result.scalars().all())

    async def get_cycle_progress(self, strategy_id: str) -> dict:
        """Retorna progreso del ciclo activo para el dashboard."""
        cycle = await self.get_or_create_active_cycle(strategy_id)
        config = STRATEGIES.get(strategy_id)
        threshold = config.trades_per_improvement_cycle if config else 20

        return {
            "cycle_number": cycle.cycle_number,
            "trades_in_cycle": cycle.trades_in_cycle,
            "trades_needed": threshold,
            "status": cycle.status,
        }

    def _format_trades_for_prompt(self, trades: list[Trade]) -> str:
        """Formatea trades para incluir en el prompt del LLM."""
        lines = []
        for t in trades:
            closed_at = t.closed_at or datetime.now(timezone.utc)
            hold_min = (closed_at - t.created_at).total_seconds() / 60
            pattern = getattr(t, "pattern_name", None) or "unknown"
            lines.append(
                f"- {t.symbol} {t.direction} | patrón: {pattern} | "
                f"hora: {t.created_at.hour:02d}:{t.created_at.minute:02d} UTC | "
                f"P&L: ${t.pnl:.4f} | duración: {hold_min:.0f}min | "
                f"size: ${t.size_usd:.2f}"
            )
        return "\n".join(lines) if lines else "Sin trades"

    def _persist_rule_to_claude_md(
        self,
        strategy_id: str,
        cycle_number: int,
        rule: ImprovementRule,
    ) -> None:
        """Escribe la regla en CLAUDE.md para persistencia cruzada."""
        # Buscar CLAUDE.md en la raíz del proyecto
        project_root = Path(__file__).resolve().parent.parent.parent
        claude_md = project_root / "CLAUDE.md"

        try:
            if not claude_md.exists():
                return  # Se creará en el Bloque 8

            content = claude_md.read_text()
            section_header = f"### {strategy_id}"

            if section_header not in content:
                return

            # Insertar la regla después del header de la estrategia
            new_rule_line = (
                f"\n{len(self._count_rules_in_md(content, strategy_id)) + 1}. "
                f"[Ciclo #{cycle_number}] {rule.description}"
            )

            # Encontrar el final de la sección de la estrategia
            idx = content.index(section_header)
            # Buscar la siguiente sección o el final
            next_section = content.find("\n### ", idx + len(section_header))
            if next_section == -1:
                insert_pos = len(content)
            else:
                insert_pos = next_section

            content = content[:insert_pos] + new_rule_line + "\n" + content[insert_pos:]
            claude_md.write_text(content)

            log.info(
                "[%s] Regla persistida en CLAUDE.md: %s",
                strategy_id, rule.pattern_name,
            )
        except Exception:
            log.debug("No se pudo persistir regla en CLAUDE.md (no crítico)")

    @staticmethod
    def _count_rules_in_md(content: str, strategy_id: str) -> list[str]:
        """Cuenta reglas existentes en CLAUDE.md para una estrategia."""
        rules = []
        in_section = False
        for line in content.split("\n"):
            if line.strip().startswith(f"### {strategy_id}"):
                in_section = True
                continue
            elif line.strip().startswith("### ") and in_section:
                break
            elif in_section and line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                rules.append(line.strip())
        return rules

    async def _call_llm_for_json(self, prompt: str) -> dict | list | None:
        """Llama al LLM Gemini y parsea la respuesta JSON."""
        import httpx
        from app.config import settings

        if not settings.gemini_api_key:
            log.error("GEMINI_API_KEY no configurada para improvement engine")
            return None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{settings.gemini_fallback_model}:generateContent"
        )

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]},
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    url, params={"key": settings.gemini_api_key}, json=payload,
                )
                resp.raise_for_status()

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [p for p in parts if "text" in p and not p.get("thought", False)]
            if not text_parts:
                text_parts = [p for p in parts if "text" in p]
            if not text_parts:
                return None

            text = text_parts[0].get("text", "").strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(ln for ln in lines if not ln.strip().startswith("```"))

            return json.loads(text)

        except Exception:
            log.exception("Error en LLM call para improvement engine")
            return None
