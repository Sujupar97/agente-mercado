import { motion } from 'framer-motion';
import {
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  CurrencyDollarIcon,
} from '@heroicons/react/24/outline';

const STATUS_COLORS = {
  positive: 'from-emerald-500/20 to-emerald-600/5 border-emerald-500/30',
  negative: 'from-red-500/20 to-red-600/5 border-red-500/30',
  neutral: 'from-blue-500/20 to-blue-600/5 border-blue-500/30',
};

export function StrategyCard({ strategy, onClick, index }) {
  const pnl = strategy.total_pnl || 0;
  const status = pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : 'neutral';
  const totalTrades = strategy.trades_won + strategy.trades_lost;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      onClick={onClick}
      className={`relative overflow-hidden rounded-2xl border bg-gradient-to-br ${STATUS_COLORS[status]}
        backdrop-blur-xl cursor-pointer hover:scale-[1.02] transition-transform duration-200`}
    >
      <div className="p-5 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-white font-bold text-lg">{strategy.name}</h3>
            <p className="text-gray-400 text-xs mt-0.5 line-clamp-2">
              {strategy.description}
            </p>
          </div>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold ${
              strategy.enabled
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-gray-700 text-gray-400'
            }`}
          >
            {strategy.enabled ? 'Activa' : 'Inactiva'}
          </span>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-3">
          <div>
            <p className="text-xs text-gray-500">Capital</p>
            <p className="text-sm font-bold text-white">
              ${strategy.capital_usd?.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">P&L</p>
            <p
              className={`text-sm font-bold ${
                pnl > 0 ? 'text-emerald-400' : pnl < 0 ? 'text-red-400' : 'text-gray-300'
              }`}
            >
              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Win Rate</p>
            <p className="text-sm font-bold text-white">
              {(strategy.win_rate * 100).toFixed(0)}%
            </p>
          </div>
        </div>

        {/* Bottom row */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center space-x-3 text-gray-400">
            <span>{totalTrades} trades</span>
            <span>{strategy.positions_open} abiertas</span>
          </div>
          <div className="flex items-center">
            {pnl > 0 ? (
              <ArrowTrendingUpIcon className="w-4 h-4 text-emerald-400" />
            ) : pnl < 0 ? (
              <ArrowTrendingDownIcon className="w-4 h-4 text-red-400" />
            ) : (
              <CurrencyDollarIcon className="w-4 h-4 text-gray-400" />
            )}
          </div>
        </div>

        {/* Improvement cycle progress */}
        {strategy.improvement_cycle && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-400">
                Ciclo #{strategy.improvement_cycle.cycle_number}
              </span>
              <span className="text-gray-500">
                {strategy.improvement_cycle.trades_in_cycle}/{strategy.improvement_cycle.trades_needed}
              </span>
            </div>
            <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500/70 rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(
                    (strategy.improvement_cycle.trades_in_cycle / strategy.improvement_cycle.trades_needed) * 100,
                    100
                  )}%`,
                }}
              />
            </div>
            {strategy.active_rules_count > 0 && (
              <p className="text-xs text-amber-400/80">
                {strategy.active_rules_count} regla{strategy.active_rules_count !== 1 ? 's' : ''} activa{strategy.active_rules_count !== 1 ? 's' : ''}
              </p>
            )}
          </div>
        )}

        {/* Status text from learning system */}
        {strategy.status_text && (
          <div className="bg-gray-900/50 rounded-lg p-2.5 border border-gray-700/30">
            <p className="text-xs text-gray-300 italic">
              {strategy.status_text}
            </p>
          </div>
        )}
      </div>
    </motion.div>
  );
}
