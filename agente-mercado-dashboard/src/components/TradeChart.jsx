import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, LineStyle, CandlestickSeries } from 'lightweight-charts';
import { api } from '../api/endpoints';
import { XMarkIcon } from '@heroicons/react/24/outline';

const LINE_STYLES = {
  0: LineStyle.Solid,
  1: LineStyle.Dashed,
  2: LineStyle.Dotted,
};

export function TradeChart({ tradeId, onClose }) {
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch chart data
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getTradeChartData(tradeId)
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.response?.data?.detail || 'Error cargando datos');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [tradeId]);

  // Render chart
  useEffect(() => {
    if (!data || !chartContainerRef.current || !data.candles?.length) return;

    const container = chartContainerRef.current;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f1117' },
        textColor: '#9ca3af',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: '#374151',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: false,
      },
      width: container.clientWidth,
      height: 400,
    });

    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      wickUpColor: '#22c55e',
    });

    candleSeries.setData(data.candles);

    // Price lines (entry, SL, TP, exit)
    for (const line of data.price_lines) {
      candleSeries.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: line.label === 'Entrada' ? 2 : 1,
        lineStyle: LINE_STYLES[line.line_style] ?? LineStyle.Dashed,
        axisLabelVisible: true,
        title: line.label,
      });
    }

    // Markers (entry/exit arrows)
    if (data.markers?.length) {
      // Snap markers to nearest candle time
      const candleTimes = data.candles.map(c => c.time);
      const snappedMarkers = data.markers.map(m => {
        const nearest = candleTimes.reduce((prev, curr) =>
          Math.abs(curr - m.time) < Math.abs(prev - m.time) ? curr : prev
        );
        return { ...m, time: nearest };
      }).sort((a, b) => a.time - b.time);

      candleSeries.setMarkers(snappedMarkers);
    }

    // Fit content
    chart.timeScale().fitContent();

    // Resize handler
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  const pnlColor = data?.pnl > 0 ? 'text-emerald-400' : data?.pnl < 0 ? 'text-red-400' : 'text-gray-400';
  const decimals = data?.entry_price >= 100 ? 2 : 5;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700/50 rounded-2xl w-full max-w-4xl overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-700/50">
          <div className="flex items-center space-x-3">
            {data && (
              <>
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                  data.direction === 'BUY'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'bg-red-500/20 text-red-400'
                }`}>
                  {data.direction === 'BUY' ? 'COMPRA' : 'VENTA'}
                </span>
                <span className="text-white font-semibold">{data.symbol}</span>
                <span className="text-xs text-gray-500">{data.timeframe}</span>
                {data.pattern_name && (
                  <span className="text-xs px-2 py-0.5 rounded bg-blue-500/15 text-blue-400">
                    {data.pattern_name}
                  </span>
                )}
              </>
            )}
          </div>
          <div className="flex items-center space-x-4">
            {data?.pnl != null && (
              <span className={`text-sm font-bold ${pnlColor}`}>
                {data.pnl >= 0 ? '+' : ''}${data.pnl.toFixed(2)}
              </span>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-800 transition-colors"
            >
              <XMarkIcon className="w-5 h-5 text-gray-400" />
            </button>
          </div>
        </div>

        {/* Trade info bar */}
        {data && (
          <div className="flex items-center space-x-6 px-5 py-2 bg-gray-800/30 text-xs">
            <div>
              <span className="text-gray-500">Entrada: </span>
              <span className="text-blue-400 font-medium">{data.entry_price.toFixed(decimals)}</span>
            </div>
            {data.stop_loss && (
              <div>
                <span className="text-gray-500">SL: </span>
                <span className="text-red-400 font-medium">{data.stop_loss.toFixed(decimals)}</span>
              </div>
            )}
            {data.take_profit && (
              <div>
                <span className="text-gray-500">TP: </span>
                <span className="text-emerald-400 font-medium">{data.take_profit.toFixed(decimals)}</span>
              </div>
            )}
            {data.exit_price && (
              <div>
                <span className="text-gray-500">Salida: </span>
                <span className="text-amber-400 font-medium">{data.exit_price.toFixed(decimals)}</span>
              </div>
            )}
            {data.entry_time && (
              <div>
                <span className="text-gray-500">Apertura: </span>
                <span className="text-gray-300">
                  {new Date(data.entry_time).toLocaleString('es', {
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                  })}
                </span>
              </div>
            )}
            {data.exit_time && (
              <div>
                <span className="text-gray-500">Cierre: </span>
                <span className="text-gray-300">
                  {new Date(data.exit_time).toLocaleString('es', {
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                  })}
                </span>
              </div>
            )}
            <div>
              <span className={`px-1.5 py-0.5 rounded ${
                data.status === 'OPEN'
                  ? 'bg-blue-500/15 text-blue-400'
                  : data.pnl > 0
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'bg-red-500/15 text-red-400'
              }`}>
                {data.status === 'OPEN' ? 'Abierta' : data.pnl > 0 ? 'Ganada' : 'Perdida'}
              </span>
            </div>
          </div>
        )}

        {/* Chart area */}
        <div className="p-2">
          {loading && (
            <div className="flex items-center justify-center h-[400px]">
              <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center h-[400px]">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}
          {!loading && !error && data && !data.candles?.length && (
            <div className="flex items-center justify-center h-[400px]">
              <p className="text-gray-500 text-sm">Sin datos de velas disponibles para este trade</p>
            </div>
          )}
          <div ref={chartContainerRef} />
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center space-x-6 px-5 py-2 border-t border-gray-700/30 text-xs">
          <div className="flex items-center space-x-1.5">
            <div className="w-3 h-0.5 bg-blue-500" style={{ borderTop: '2px dotted #3b82f6' }} />
            <span className="text-gray-500">Entrada</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className="w-3 h-0.5" style={{ borderTop: '2px dashed #ef4444' }} />
            <span className="text-gray-500">Stop Loss</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className="w-3 h-0.5" style={{ borderTop: '2px dashed #22c55e' }} />
            <span className="text-gray-500">Take Profit</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className="w-3 h-0.5 bg-amber-500" />
            <span className="text-gray-500">Salida</span>
          </div>
        </div>
      </div>
    </div>
  );
}
