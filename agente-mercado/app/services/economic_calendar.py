"""Servicio de calendario económico — protección contra noticias high-impact.

Usa Forex Factory RSS feed (gratis, sin auth) como fuente principal.
Cache de eventos del día (refresh cada 6h).

Eventos high-impact típicos:
- NFP (Non-Farm Payrolls) — primer viernes 13:30 UTC
- FOMC Rate Decision — variable
- CPI / Inflation — mensual
- GDP — trimestral
- Central Bank Speeches (Powell, Lagarde, etc.)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)


# Currencies que afectan a nuestros instrumentos (EUR/USD, GBP/USD, USD/JPY, XAU/USD)
TRACKED_CURRENCIES = {"USD", "EUR", "GBP", "JPY"}

# Keywords que indican high-impact (Forex Factory no siempre marca correctamente)
HIGH_IMPACT_KEYWORDS = [
    "non-farm", "nfp", "nonfarm",
    "fomc", "fed", "powell",
    "cpi", "inflation",
    "gdp",
    "rate decision", "interest rate",
    "ecb", "lagarde",
    "boe", "bailey",
    "boj", "ueda",
    "unemployment",
    "retail sales",
    "ppi", "pce",
]


@dataclass(frozen=True)
class NewsEvent:
    """Evento económico con potencial de mover el mercado."""

    time: datetime  # UTC
    currency: str  # USD, EUR, GBP, JPY
    title: str
    impact: str  # "high" | "medium" | "low"

    def affects_instrument(self, instrument: str) -> bool:
        """Verifica si este evento afecta al instrumento dado."""
        # EUR_USD afecta tanto EUR como USD
        parts = instrument.replace("XAU", "USD").split("_")
        return self.currency in parts


class EconomicCalendarService:
    """Servicio que mantiene un cache de eventos económicos del día."""

    _CACHE_TTL_HOURS = 6
    _FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(self) -> None:
        self._events: list[NewsEvent] = []
        self._cached_at: datetime | None = None

    async def get_events_today(self) -> list[NewsEvent]:
        """Retorna eventos high-impact del día actual."""
        await self._refresh_if_needed()

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        return [e for e in self._events if today_start <= e.time < today_end]

    async def _refresh_if_needed(self) -> None:
        """Refresca el cache si tiene más de 6h."""
        if self._cached_at is not None:
            age_hours = (datetime.now(timezone.utc) - self._cached_at).total_seconds() / 3600
            if age_hours < self._CACHE_TTL_HOURS:
                return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self._FOREX_FACTORY_URL)
                resp.raise_for_status()
                data = resp.json()

            self._events = self._parse_forex_factory(data)
            self._cached_at = datetime.now(timezone.utc)
            log.info(
                "Calendario económico cargado: %d eventos high-impact esta semana",
                len(self._events),
            )
        except Exception:
            log.exception("Error cargando calendario económico — usando cache previo o vacío")

    def _parse_forex_factory(self, data: list[dict]) -> list[NewsEvent]:
        """Parsea respuesta JSON de Forex Factory."""
        events: list[NewsEvent] = []

        for item in data:
            currency = item.get("country", "").upper()
            if currency not in TRACKED_CURRENCIES:
                continue

            impact = item.get("impact", "").lower()
            title = item.get("title", "")

            # Filter: high-impact (por flag o por keywords)
            is_high = impact == "high" or any(
                kw in title.lower() for kw in HIGH_IMPACT_KEYWORDS
            )
            if not is_high:
                continue

            # Parse datetime: formato "2026-04-04T13:30:00-04:00"
            date_str = item.get("date", "")
            try:
                event_time = datetime.fromisoformat(date_str)
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                else:
                    event_time = event_time.astimezone(timezone.utc)
            except (ValueError, TypeError):
                continue

            events.append(NewsEvent(
                time=event_time,
                currency=currency,
                title=title,
                impact="high",
            ))

        return events

    async def is_blackout(
        self,
        instrument: str,
        now: datetime | None = None,
        minutes_before: int = 5,
        minutes_after: int = 15,
    ) -> tuple[bool, NewsEvent | None]:
        """Verifica si estamos en ventana de blackout para el instrumento.

        Args:
            instrument: ej. "EUR_USD"
            now: hora a evaluar (default: now UTC)
            minutes_before: minutos antes del evento que activa blackout
            minutes_after: minutos después del evento que sigue blackout

        Returns:
            (en_blackout, evento_que_causa_blackout)
        """
        if now is None:
            now = datetime.now(timezone.utc)

        events = await self.get_events_today()
        for event in events:
            if not event.affects_instrument(instrument):
                continue

            delta_minutes = (event.time - now).total_seconds() / 60
            if -minutes_after <= delta_minutes <= minutes_before:
                return True, event

        return False, None

    async def upcoming_event_for(
        self,
        instrument: str,
        within_minutes: int = 5,
        now: datetime | None = None,
    ) -> NewsEvent | None:
        """Retorna evento próximo (dentro de N min) que afecta al instrumento.

        Útil para cerrar posiciones antes de news.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        events = await self.get_events_today()
        for event in events:
            if not event.affects_instrument(instrument):
                continue
            delta_minutes = (event.time - now).total_seconds() / 60
            if 0 < delta_minutes <= within_minutes:
                return event

        return None
