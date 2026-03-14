"""Criterio de Kelly — cálculo de fracción óptima para trades."""

from __future__ import annotations


def kelly_crypto(
    p_win: float,
    take_profit_pct: float,
    stop_loss_pct: float,
) -> float:
    """
    Criterio de Kelly para trades cripto con take-profit y stop-loss.

    Args:
        p_win: Probabilidad estimada de alcanzar TP antes de SL (0-1).
        take_profit_pct: Ganancia esperada como decimal (e.g., 0.04 = 4%).
        stop_loss_pct: Pérdida máxima como decimal (e.g., 0.02 = 2%).

    Returns:
        Fracción óptima del capital a asignar (0-1). 0 si no hay edge.
    """
    if p_win <= 0 or p_win >= 1:
        return 0.0
    if take_profit_pct <= 0 or stop_loss_pct <= 0:
        return 0.0

    q = 1 - p_win
    b = take_profit_pct / stop_loss_pct  # ratio reward/risk

    # f* = (p * b - q) / b
    kelly = (p_win * b - q) / b

    return max(0.0, kelly)


def kelly_prediction(
    p_estimated: float,
    market_price: float,
    direction: str,
) -> float:
    """
    Criterio de Kelly para mercados binarios de predicción (Polymarket).

    Args:
        p_estimated: Probabilidad estimada por el agente (0-1).
        market_price: Precio YES del mercado (0-1) = probabilidad implícita.
        direction: "BUY_YES" o "BUY_NO".

    Returns:
        Fracción óptima (0-1). 0 si no hay edge.
    """
    if p_estimated <= 0 or p_estimated >= 1:
        return 0.0
    if market_price <= 0 or market_price >= 1:
        return 0.0

    if direction == "BUY_YES":
        p = p_estimated
        q = 1 - p
        b = (1 - market_price) / market_price
    elif direction == "BUY_NO":
        p = 1 - p_estimated
        q = p_estimated
        b = market_price / (1 - market_price)
    else:
        return 0.0

    kelly = (p * b - q) / b
    return max(0.0, kelly)


def size_position(
    kelly_fraction: float,
    capital: float,
    fractional_kelly: float = 0.25,
    max_pct: float = 0.03,
) -> float:
    """
    Aplica Kelly fraccional + hard cap para calcular tamaño de posición.

    Args:
        kelly_fraction: Fracción Kelly pura (de kelly_crypto o kelly_prediction).
        capital: Capital disponible en USD.
        fractional_kelly: Fracción del Kelly a usar (default 0.25 = conservador).
        max_pct: Máximo % del capital por trade (default 3%).

    Returns:
        Tamaño de posición en USD.
    """
    adjusted = kelly_fraction * fractional_kelly
    capped = min(adjusted, max_pct)
    return capital * capped
