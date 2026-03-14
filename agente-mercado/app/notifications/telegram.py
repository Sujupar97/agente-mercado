"""Notificaciones via Telegram Bot API."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)


class TelegramNotifier:
    """Envía alertas via Telegram."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._enabled = bool(settings.telegram_bot_token and settings.telegram_chat_id)
        if not self._enabled:
            log.info("Telegram: deshabilitado (sin token o chat_id)")

    async def send(self, message: str) -> bool:
        """Envía un mensaje de texto."""
        if not self._enabled:
            log.info("Telegram (no enviado): %s", message[:100])
            return False

        try:
            resp = await self._client.post(
                f"{self.BASE_URL}/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
            )
            resp.raise_for_status()
            return True
        except Exception:
            log.exception("Error enviando mensaje Telegram")
            return False

    async def send_trade_alert(
        self,
        direction: str,
        symbol: str,
        size_usd: float,
        entry_price: float,
        kelly_pct: float,
    ) -> bool:
        """Envía alerta de trade ejecutado."""
        msg = (
            f"<b>Trade Ejecutado</b>\n"
            f"{direction} {symbol}\n"
            f"Tamaño: ${size_usd:.2f}\n"
            f"Precio: ${entry_price:.4f}\n"
            f"Kelly: {kelly_pct:.1%}"
        )
        return await self.send(msg)

    async def send_status_change(self, old_mode: str, new_mode: str, reason: str) -> bool:
        """Envía alerta de cambio de estado."""
        msg = (
            f"<b>Cambio de Estado</b>\n"
            f"{old_mode} → {new_mode}\n"
            f"Razón: {reason}"
        )
        return await self.send(msg)

    async def send_cycle_summary(
        self,
        markets_scanned: int,
        signals: int,
        trades: int,
        capital: float,
        pnl_today: float,
    ) -> bool:
        """Envía resumen del ciclo (solo si hay trades)."""
        if trades == 0:
            return False
        msg = (
            f"<b>Ciclo Completado</b>\n"
            f"Mercados: {markets_scanned}\n"
            f"Señales: {signals}\n"
            f"Trades: {trades}\n"
            f"Capital: ${capital:.2f}\n"
            f"P&L hoy: ${pnl_today:.2f}"
        )
        return await self.send(msg)

    async def close(self) -> None:
        await self._client.aclose()
