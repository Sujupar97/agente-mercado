"""Renderiza un gráfico de velas con entry/SL/TP marcados como PNG.

Usado por el vision validator para que Claude pueda "ver" la entrada antes de
ejecutar el trade.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")  # Backend sin display, necesario en servidor

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from app.broker.models import Candle

log = logging.getLogger(__name__)


@dataclass
class ChartLines:
    """Líneas horizontales a dibujar (entry/SL/TP)."""

    entry: float
    stop_loss: float
    take_profit: float
    direction: str  # "LONG" | "SHORT"


def render_chart(
    instrument: str,
    candles: list[Candle],
    lines: ChartLines,
    title_suffix: str = "",
) -> bytes:
    """Genera PNG del gráfico con velas + EMA20 + entry/SL/TP marcados.

    Args:
        instrument: ej "EUR_USD"
        candles: lista de velas (las últimas 50-100 son ideales)
        lines: niveles entry/SL/TP a marcar
        title_suffix: texto adicional para el título

    Returns:
        bytes del PNG
    """
    if not candles or len(candles) < 5:
        raise ValueError(f"Insuficientes candles para renderizar: {len(candles)}")

    # Tomar últimas 60 velas para contexto visual
    recent = candles[-60:]

    # Construir DataFrame para mplfinance
    df = pd.DataFrame([
        {
            "Date": c.timestamp,
            "Open": c.open,
            "High": c.high,
            "Low": c.low,
            "Close": c.close,
            "Volume": getattr(c, "volume", 0) or 0,
        }
        for c in recent
    ])
    df.set_index("Date", inplace=True)

    # EMA20 para contexto
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

    # Líneas horizontales
    hlines = dict(
        hlines=[lines.entry, lines.stop_loss, lines.take_profit],
        colors=["#3b82f6", "#ef4444", "#22c55e"],
        linewidths=[2, 1.5, 1.5],
        linestyle=["-", "--", "--"],
    )

    # Plot adicional para EMA20
    apds = [
        mpf.make_addplot(df["EMA20"], color="#f59e0b", width=1.0),
    ]

    # Estilo dark
    mc = mpf.make_marketcolors(
        up="#22c55e",
        down="#ef4444",
        edge="inherit",
        wick={"up": "#22c55e", "down": "#ef4444"},
    )
    style = mpf.make_mpf_style(
        marketcolors=mc,
        facecolor="#0f1117",
        edgecolor="#374151",
        gridcolor="#1f2937",
        gridstyle=":",
        rc={"axes.labelcolor": "#9ca3af", "xtick.color": "#9ca3af", "ytick.color": "#9ca3af"},
    )

    title = f"{instrument} {lines.direction} {title_suffix}".strip()

    fig, _ = mpf.plot(
        df,
        type="candle",
        style=style,
        title=title,
        addplot=apds,
        hlines=hlines,
        figsize=(10, 6),
        returnfig=True,
        tight_layout=True,
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=80, bbox_inches="tight", facecolor="#0f1117")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
