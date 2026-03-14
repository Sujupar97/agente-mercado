"""Motor de ejecución de órdenes — via ccxt (Binance/Bybit)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import ccxt.async_support as ccxt

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class TradeOrder:
    """Orden a ejecutar."""

    symbol: str  # "BTC/USDT"
    direction: str  # "BUY" | "SELL"
    size_usd: float
    take_profit_pct: float
    stop_loss_pct: float
    kelly_fraction: float
    signal_id: int | None = None


@dataclass
class TradeResult:
    """Resultado de la ejecución de una orden."""

    success: bool
    order_id: str | None = None
    symbol: str = ""
    direction: str = ""
    size_usd: float = 0.0
    quantity: float = 0.0
    entry_price: float = 0.0
    take_profit_price: float = 0.0
    stop_loss_price: float = 0.0
    fees: float = 0.0
    kelly_fraction: float = 0.0
    signal_id: int | None = None
    error: str = ""
    timestamp: datetime = None  # type: ignore

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class OrderExecutor:
    """Ejecuta órdenes de trading en exchanges cripto via ccxt."""

    def __init__(self) -> None:
        self._exchange: ccxt.Exchange | None = None
        self._init_exchange()

    def _init_exchange(self) -> None:
        """Inicializa el exchange principal (Binance por defecto)."""
        config = {
            "enableRateLimit": True,
        }

        if settings.binance_api_key:
            config["apiKey"] = settings.binance_api_key
            config["secret"] = settings.binance_api_secret
            if settings.binance_testnet:
                config["sandbox"] = True
            self._exchange = ccxt.binance(config)
            log.info("Executor: Binance configurado (testnet=%s)", settings.binance_testnet)
        elif settings.bybit_api_key:
            config["apiKey"] = settings.bybit_api_key
            config["secret"] = settings.bybit_api_secret
            self._exchange = ccxt.bybit(config)
            log.info("Executor: Bybit configurado")
        else:
            log.warning("Executor: Sin API keys de exchange — solo modo simulación")

    async def execute(self, order: TradeOrder) -> TradeResult:
        """Ejecuta una orden limit en el exchange."""
        if not self._exchange:
            return TradeResult(
                success=False, error="No hay exchange configurado",
                symbol=order.symbol, direction=order.direction,
            )

        try:
            # Obtener precio actual para calcular limit price
            ticker = await self._exchange.fetch_ticker(order.symbol)
            current_price = ticker.get("last", 0)
            if current_price <= 0:
                return TradeResult(
                    success=False, error=f"Precio inválido: {current_price}",
                    symbol=order.symbol, direction=order.direction,
                )

            # Calcular cantidad
            quantity = order.size_usd / current_price

            # Precio de la orden limit (ligeramente favorable)
            if order.direction == "BUY":
                # Comprar un poco por debajo del ask
                limit_price = ticker.get("ask", current_price) * 0.999
                tp_price = current_price * (1 + order.take_profit_pct)
                sl_price = current_price * (1 - order.stop_loss_pct)
            else:
                # Vender un poco por encima del bid
                limit_price = ticker.get("bid", current_price) * 1.001
                tp_price = current_price * (1 - order.take_profit_pct)
                sl_price = current_price * (1 + order.stop_loss_pct)

            # Redondear según la precisión del exchange
            market_info = self._exchange.market(order.symbol)
            precision = market_info.get("precision", {})
            amount_precision = precision.get("amount", 8)
            price_precision = precision.get("price", 8)

            quantity = round(quantity, amount_precision)
            limit_price = round(limit_price, price_precision)

            # Ejecutar orden limit
            side = order.direction.lower()
            result = await self._exchange.create_order(
                symbol=order.symbol,
                type="limit",
                side=side,
                amount=quantity,
                price=limit_price,
            )

            order_id = result.get("id", "")
            filled_price = result.get("average") or result.get("price") or limit_price
            fees_raw = result.get("fee", {})
            fees_usd = fees_raw.get("cost", 0) if fees_raw else 0

            log.info(
                "Orden ejecutada: %s %s %.6f @ $%.4f (orden=%s, fees=$%.4f)",
                order.direction, order.symbol, quantity, filled_price, order_id, fees_usd,
            )

            return TradeResult(
                success=True,
                order_id=order_id,
                symbol=order.symbol,
                direction=order.direction,
                size_usd=order.size_usd,
                quantity=quantity,
                entry_price=filled_price,
                take_profit_price=tp_price,
                stop_loss_price=sl_price,
                fees=fees_usd,
                kelly_fraction=order.kelly_fraction,
                signal_id=order.signal_id,
            )

        except ccxt.InsufficientFunds:
            log.error("Fondos insuficientes para %s %s", order.direction, order.symbol)
            return TradeResult(
                success=False, error="Fondos insuficientes",
                symbol=order.symbol, direction=order.direction,
            )
        except ccxt.InvalidOrder as e:
            log.error("Orden inválida %s %s: %s", order.direction, order.symbol, e)
            return TradeResult(
                success=False, error=f"Orden inválida: {e}",
                symbol=order.symbol, direction=order.direction,
            )
        except Exception:
            log.exception("Error ejecutando orden %s %s", order.direction, order.symbol)
            return TradeResult(
                success=False, error="Error inesperado",
                symbol=order.symbol, direction=order.direction,
            )

    async def close_position(self, symbol: str, direction: str, quantity: float) -> TradeResult:
        """Cierra una posición abierta."""
        close_side = "SELL" if direction == "BUY" else "BUY"
        order = TradeOrder(
            symbol=symbol,
            direction=close_side,
            size_usd=0,  # Se calcula por quantity
            take_profit_pct=0,
            stop_loss_pct=0,
            kelly_fraction=0,
        )
        try:
            if not self._exchange:
                return TradeResult(success=False, error="No exchange")

            result = await self._exchange.create_order(
                symbol=symbol,
                type="market",
                side=close_side.lower(),
                amount=quantity,
            )
            filled_price = result.get("average") or result.get("price") or 0
            return TradeResult(
                success=True,
                order_id=result.get("id"),
                symbol=symbol,
                direction=close_side,
                entry_price=filled_price,
                quantity=quantity,
            )
        except Exception:
            log.exception("Error cerrando posición %s %s", symbol, direction)
            return TradeResult(success=False, error="Error cerrando posición")

    async def close_all_positions(self, open_trades: list[dict]) -> None:
        """Cierra todas las posiciones abiertas (emergencia)."""
        for trade in open_trades:
            await self.close_position(
                symbol=trade["symbol"],
                direction=trade["direction"],
                quantity=trade["quantity"],
            )

    async def close(self) -> None:
        if self._exchange:
            await self._exchange.close()
