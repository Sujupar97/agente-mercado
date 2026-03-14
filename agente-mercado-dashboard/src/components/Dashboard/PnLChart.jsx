import { motion } from 'framer-motion';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  const data = payload[0].payload;
  return (
    <div className="bg-gray-900/95 backdrop-blur-xl border border-gray-700/50 rounded-lg p-3 shadow-xl">
      <p className="text-xs text-gray-400 mb-2">{label}</p>
      <div className="space-y-1">
        <div className="flex justify-between space-x-6">
          <span className="text-xs text-gray-400">Capital</span>
          <span className="text-xs font-semibold text-white">${data.capital?.toFixed(2)}</span>
        </div>
        <div className="flex justify-between space-x-6">
          <span className="text-xs text-gray-400">Ganancia</span>
          <span className={`text-xs font-semibold ${data.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {data.pnl >= 0 ? '+' : ''}${data.pnl?.toFixed(2)}
          </span>
        </div>
        <div className="flex justify-between space-x-6">
          <span className="text-xs text-gray-400">Neto</span>
          <span className={`text-xs font-semibold ${data.net >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {data.net >= 0 ? '+' : ''}${data.net?.toFixed(2)}
          </span>
        </div>
        <div className="flex justify-between space-x-6">
          <span className="text-xs text-gray-400">Operaciones</span>
          <span className="text-xs text-gray-300">{data.trades_count}</span>
        </div>
      </div>
    </div>
  );
}

export function PnLChart({ pnlHistory, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-700/50 rounded w-56 mb-4" />
          <div className="h-64 bg-gray-700/20 rounded" />
        </div>
      </div>
    );
  }

  const data = pnlHistory?.history || [];
  const hasData = data.some(d => d.trades_count > 0 || d.pnl !== 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.15 }}
      className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl overflow-hidden"
    >
      <div className="px-6 py-4 border-b border-gray-700/50">
        <h2 className="text-lg font-semibold text-white">Capital Historico (30 dias)</h2>
      </div>

      <div className="p-4">
        {!hasData ? (
          <div className="h-64 flex items-center justify-center">
            <p className="text-gray-500 text-sm">Los datos del grafico apareceran cuando se ejecuten operaciones</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorCapital" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="date"
                stroke="#4b5563"
                tick={{ fill: '#6b7280', fontSize: 11 }}
                tickFormatter={(val) => {
                  const parts = val.split('-');
                  return `${parts[1]}/${parts[2]}`;
                }}
              />
              <YAxis
                stroke="#4b5563"
                tick={{ fill: '#6b7280', fontSize: 11 }}
                tickFormatter={(val) => `$${val}`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="capital"
                stroke="#3b82f6"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorCapital)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </motion.div>
  );
}
