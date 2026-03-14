import { motion } from 'framer-motion';
import {
  AcademicCapIcon,
  ChartBarIcon,
  AdjustmentsHorizontalIcon,
  ClockIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  BeakerIcon,
} from '@heroicons/react/24/outline';
import {
  useLearningPerformance,
  useLearningSymbols,
  useLearningAdjustments,
  useLearningLog,
} from '../../hooks/useLearning';

function MetricCard({ label, value, subtext, color = 'text-white', icon: Icon }) {
  return (
    <div className="rounded-lg border border-gray-700/30 bg-gray-800/40 p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-400">{label}</span>
        {Icon && <Icon className={`w-4 h-4 ${color}`} />}
      </div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      {subtext && <div className="text-xs text-gray-500 mt-0.5">{subtext}</div>}
    </div>
  );
}

function CalibrationBar({ bucket }) {
  const predicted = Math.round(bucket.predicted_win_rate * 100);
  const actual = Math.round(bucket.actual_win_rate * 100);
  const isOverestimate = predicted > actual;

  return (
    <div className="flex items-center space-x-3 py-2 border-b border-gray-800/50 last:border-0">
      <div className="w-24 text-xs text-gray-400 shrink-0">
        {bucket.confidence_range}
      </div>
      <div className="flex-1">
        <div className="flex items-center space-x-2 mb-1">
          <div className="flex-1 bg-gray-800 rounded-full h-2 overflow-hidden">
            <div
              className="bg-blue-500/60 h-full rounded-full"
              style={{ width: `${Math.min(predicted, 100)}%` }}
            />
          </div>
          <span className="text-xs text-blue-400 w-8 text-right">{predicted}%</span>
        </div>
        <div className="flex items-center space-x-2">
          <div className="flex-1 bg-gray-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full rounded-full ${actual >= predicted ? 'bg-emerald-500/60' : 'bg-red-500/60'}`}
              style={{ width: `${Math.min(actual, 100)}%` }}
            />
          </div>
          <span className={`text-xs w-8 text-right ${actual >= predicted ? 'text-emerald-400' : 'text-red-400'}`}>
            {actual}%
          </span>
        </div>
      </div>
      <div className="w-16 text-right">
        <span className="text-xs text-gray-500">{bucket.trade_count} trades</span>
      </div>
    </div>
  );
}

function SymbolRow({ symbol, rank }) {
  const isPositive = symbol.total_pnl > 0;

  return (
    <motion.tr
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: rank * 0.03 }}
      className="border-b border-gray-800/30 hover:bg-gray-800/30 transition-colors"
    >
      <td className="py-2 px-3 text-sm font-mono text-white">{symbol.symbol}</td>
      <td className="py-2 px-3 text-sm text-center">{symbol.total_trades}</td>
      <td className="py-2 px-3 text-sm text-center">
        <span className={symbol.win_rate >= 0.5 ? 'text-emerald-400' : 'text-red-400'}>
          {Math.round(symbol.win_rate * 100)}%
        </span>
      </td>
      <td className={`py-2 px-3 text-sm text-right font-mono ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
        {isPositive ? '+' : ''}${symbol.total_pnl.toFixed(4)}
      </td>
      <td className="py-2 px-3 text-sm text-right text-gray-400">
        {symbol.profit_factor === Infinity ? '---' : symbol.profit_factor.toFixed(2)}
      </td>
      <td className="py-2 px-3 text-sm text-right text-gray-400">
        {Math.round(symbol.avg_hold_minutes)}m
      </td>
    </motion.tr>
  );
}

function AdjustmentCard({ adjustment }) {
  const typeConfig = {
    BLACKLIST_SYMBOL: { icon: XCircleIcon, color: 'text-red-400', bg: 'bg-red-500/10' },
    BOOST_SYMBOL: { icon: CheckCircleIcon, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    RAISE_MIN_CONFIDENCE: { icon: AdjustmentsHorizontalIcon, color: 'text-amber-400', bg: 'bg-amber-500/10' },
    DIRECTION_BIAS: { icon: ArrowTrendingUpIcon, color: 'text-blue-400', bg: 'bg-blue-500/10' },
    AVOID_HOUR: { icon: ClockIcon, color: 'text-orange-400', bg: 'bg-orange-500/10' },
  };

  const config = typeConfig[adjustment.type] || typeConfig.RAISE_MIN_CONFIDENCE;
  const Icon = config.icon;

  return (
    <div className={`rounded-lg border border-gray-700/30 ${config.bg} p-3`}>
      <div className="flex items-start space-x-3">
        <Icon className={`w-5 h-5 ${config.color} shrink-0 mt-0.5`} />
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${config.color}`}>
            {adjustment.type.replace(/_/g, ' ')}
            {adjustment.symbol && ` — ${adjustment.symbol}`}
            {adjustment.direction && ` — ${adjustment.direction}`}
            {adjustment.hour >= 0 && adjustment.type === 'AVOID_HOUR' && ` — ${adjustment.hour}:00 UTC`}
          </div>
          <div className="text-xs text-gray-400 mt-0.5">{adjustment.reason}</div>
        </div>
      </div>
    </div>
  );
}

export function LearningPage() {
  const { data: performance, isLoading: perfLoading } = useLearningPerformance();
  const { data: symbols, isLoading: symLoading } = useLearningSymbols();
  const { data: adjustments } = useLearningAdjustments();
  const { data: logs } = useLearningLog();

  if (perfLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  const hasSufficientData = performance?.data_sufficient !== false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6"
      >
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold text-white inline-flex items-center">
            <AcademicCapIcon className="w-5 h-5 mr-2 text-blue-400" />
            Sistema de Aprendizaje
          </h2>
          <span className={`text-xs px-2.5 py-1 rounded-full ${
            hasSufficientData
              ? 'bg-emerald-500/15 text-emerald-400'
              : 'bg-amber-500/15 text-amber-400'
          }`}>
            {performance?.total_trades || 0} trades analizados
          </span>
        </div>
        <p className="text-sm text-gray-400">
          {hasSufficientData
            ? 'Analisis de rendimiento activo. El agente esta aprendiendo de sus operaciones.'
            : `Recopilando datos... Se necesitan 30+ trades cerrados (actual: ${performance?.total_trades || 0}).`
          }
        </p>
      </motion.div>

      {/* Metricas Globales */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3"
      >
        <MetricCard
          label="Win Rate"
          value={`${Math.round((performance?.win_rate || 0) * 100)}%`}
          subtext={hasSufficientData ? 'tasa de acierto' : 'datos insuficientes'}
          color={(performance?.win_rate || 0) >= 0.5 ? 'text-emerald-400' : 'text-red-400'}
          icon={ChartBarIcon}
        />
        <MetricCard
          label="Profit Factor"
          value={performance?.profit_factor === Infinity ? '---' : (performance?.profit_factor || 0).toFixed(2)}
          subtext={hasSufficientData ? (performance?.profit_factor >= 1.5 ? 'bueno' : performance?.profit_factor >= 1 ? 'aceptable' : 'perdiendo') : ''}
          color={(performance?.profit_factor || 0) >= 1 ? 'text-emerald-400' : 'text-red-400'}
          icon={ArrowTrendingUpIcon}
        />
        <MetricCard
          label="Sortino"
          value={(performance?.sortino_ratio || 0).toFixed(2)}
          subtext="riesgo bajista"
          color={(performance?.sortino_ratio || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}
          icon={BeakerIcon}
        />
        <MetricCard
          label="Expectancy"
          value={`$${(performance?.expectancy || 0).toFixed(4)}`}
          subtext="por trade"
          color={(performance?.expectancy || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}
          icon={ArrowTrendingUpIcon}
        />
        <MetricCard
          label="Trades"
          value={performance?.total_trades || 0}
          subtext="analizados"
          color="text-blue-400"
          icon={AcademicCapIcon}
        />
      </motion.div>

      {/* Direccion BUY vs SELL */}
      {hasSufficientData && (performance?.buy_stats || performance?.sell_stats) && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="grid grid-cols-1 sm:grid-cols-2 gap-3"
        >
          {performance.buy_stats && (
            <div className="rounded-xl border border-gray-700/50 bg-gray-900/60 p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-emerald-400 flex items-center">
                  <ArrowTrendingUpIcon className="w-4 h-4 mr-1.5" /> BUY
                </span>
                <span className="text-xs text-gray-500">{performance.buy_stats.total_trades} trades</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-lg font-bold text-white">{Math.round(performance.buy_stats.win_rate * 100)}%</div>
                  <div className="text-xs text-gray-500">Win Rate</div>
                </div>
                <div>
                  <div className={`text-lg font-bold ${performance.buy_stats.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    ${performance.buy_stats.total_pnl.toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-500">P&L</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-white">
                    {performance.buy_stats.profit_factor === Infinity ? '---' : performance.buy_stats.profit_factor.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-500">PF</div>
                </div>
              </div>
            </div>
          )}
          {performance.sell_stats && (
            <div className="rounded-xl border border-gray-700/50 bg-gray-900/60 p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-red-400 flex items-center">
                  <ArrowTrendingDownIcon className="w-4 h-4 mr-1.5" /> SELL
                </span>
                <span className="text-xs text-gray-500">{performance.sell_stats.total_trades} trades</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-lg font-bold text-white">{Math.round(performance.sell_stats.win_rate * 100)}%</div>
                  <div className="text-xs text-gray-500">Win Rate</div>
                </div>
                <div>
                  <div className={`text-lg font-bold ${performance.sell_stats.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    ${performance.sell_stats.total_pnl.toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-500">P&L</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-white">
                    {performance.sell_stats.profit_factor === Infinity ? '---' : performance.sell_stats.profit_factor.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-500">PF</div>
                </div>
              </div>
            </div>
          )}
        </motion.div>
      )}

      {/* Calibracion de Confianza */}
      {hasSufficientData && performance?.calibration?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6"
        >
          <h3 className="text-sm font-semibold text-white mb-1">Calibracion de Confianza</h3>
          <p className="text-xs text-gray-500 mb-4">
            Azul = confianza predicha por el LLM | Color = win rate real.
            Verde = LLM subestima, Rojo = LLM sobreestima.
          </p>
          <div className="space-y-1">
            {performance.calibration.map((bucket) => (
              <CalibrationBar key={bucket.confidence_range} bucket={bucket} />
            ))}
          </div>
        </motion.div>
      )}

      {/* Ranking de Simbolos */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white">Ranking de Simbolos</h3>
          <span className="text-xs text-gray-500">min. 5 trades por simbolo</span>
        </div>
        {symbols && symbols.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-700/50">
                  <th className="py-2 px-3 text-xs text-gray-400 font-medium">Simbolo</th>
                  <th className="py-2 px-3 text-xs text-gray-400 font-medium text-center">Trades</th>
                  <th className="py-2 px-3 text-xs text-gray-400 font-medium text-center">Win Rate</th>
                  <th className="py-2 px-3 text-xs text-gray-400 font-medium text-right">P&L</th>
                  <th className="py-2 px-3 text-xs text-gray-400 font-medium text-right">PF</th>
                  <th className="py-2 px-3 text-xs text-gray-400 font-medium text-right">Hold</th>
                </tr>
              </thead>
              <tbody>
                {symbols.map((sym, i) => (
                  <SymbolRow key={sym.symbol} symbol={sym} rank={i} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500 text-sm">
            Sin datos suficientes (se requieren min. 5 trades por simbolo)
          </div>
        )}
      </motion.div>

      {/* Modelo Comparacion */}
      {hasSufficientData && performance?.model_comparison?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6"
        >
          <h3 className="text-sm font-semibold text-white mb-4">Comparacion de Modelos LLM</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {performance.model_comparison.map((model) => (
              <div key={model.model} className="rounded-lg border border-gray-700/30 bg-gray-800/40 p-4">
                <div className="text-sm font-mono text-blue-400 mb-2">
                  {model.model.includes('flash') ? 'Flash (Rutina)' : model.model.includes('pro') ? 'Pro (Profundo)' : model.model}
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div>
                    <div className="text-base font-bold text-white">{Math.round(model.win_rate * 100)}%</div>
                    <div className="text-gray-500">WR</div>
                  </div>
                  <div>
                    <div className={`text-base font-bold ${model.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ${model.total_pnl.toFixed(2)}
                    </div>
                    <div className="text-gray-500">P&L</div>
                  </div>
                  <div>
                    <div className="text-base font-bold text-white">{model.total_trades}</div>
                    <div className="text-gray-500">Trades</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Ajustes Adaptativos */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
        className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center">
            <AdjustmentsHorizontalIcon className="w-4 h-4 mr-1.5 text-amber-400" />
            Ajustes Adaptativos
          </h3>
          <span className="text-xs text-gray-500">recalculados cada hora</span>
        </div>
        {adjustments && adjustments.length > 0 ? (
          <div className="space-y-2">
            {adjustments.map((adj, i) => (
              <AdjustmentCard key={i} adjustment={adj} />
            ))}
          </div>
        ) : (
          <div className="text-center py-6 text-gray-500 text-sm">
            Sin ajustes activos (se calculan con 30+ trades)
          </div>
        )}
      </motion.div>

      {/* Recomendaciones */}
      {performance?.recommendations?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="rounded-xl border border-amber-700/30 bg-amber-500/5 backdrop-blur-xl p-6"
        >
          <h3 className="text-sm font-semibold text-amber-400 flex items-center mb-3">
            <ExclamationTriangleIcon className="w-4 h-4 mr-1.5" />
            Recomendaciones del Sistema
          </h3>
          <ul className="space-y-2">
            {performance.recommendations.map((rec, i) => (
              <li key={i} className="text-sm text-gray-300 flex items-start">
                <span className="text-amber-400 mr-2 shrink-0">-</span>
                {rec}
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      {/* Log de Aprendizaje */}
      {logs && logs.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45 }}
          className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6"
        >
          <h3 className="text-sm font-semibold text-white mb-4">Log de Aprendizaje</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {logs.map((log) => (
              <div key={log.id} className="flex items-start space-x-3 py-2 border-b border-gray-800/30 last:border-0">
                <div className="text-xs text-gray-500 w-32 shrink-0">
                  {new Date(log.created_at).toLocaleString('es', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </div>
                <div className="flex-1">
                  <span className="text-xs font-medium text-blue-400">
                    {log.adjustment_type.replace(/_/g, ' ')}
                  </span>
                  <span className="text-xs text-gray-400 ml-2">{log.parameter}</span>
                  <div className="text-xs text-gray-500 mt-0.5">{log.reason}</div>
                </div>
                <div className="text-xs text-gray-600">{log.trades_analyzed} trades</div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
