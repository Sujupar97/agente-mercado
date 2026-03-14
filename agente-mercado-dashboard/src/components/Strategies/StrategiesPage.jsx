import { useState } from 'react';
import { motion } from 'framer-motion';
import { useStrategies } from '../../hooks/useStrategies';
import { StrategyCard } from './StrategyCard';
import { StrategyDetail } from './StrategyDetail';

export function StrategiesPage() {
  const { data: strategies, isLoading } = useStrategies();
  const [selectedStrategy, setSelectedStrategy] = useState(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-gray-400">Cargando estrategias...</p>
        </div>
      </div>
    );
  }

  if (!strategies?.length) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400">No hay estrategias configuradas</p>
        <p className="text-xs text-gray-600 mt-1">
          Las estrategias se crean automaticamente al iniciar el agente
        </p>
      </div>
    );
  }

  // Detail view
  if (selectedStrategy) {
    const current = strategies.find((s) => s.id === selectedStrategy);
    if (current) {
      return (
        <StrategyDetail
          strategy={current}
          onBack={() => setSelectedStrategy(null)}
        />
      );
    }
  }

  // Summary stats
  const totalCapital = strategies.reduce((sum, s) => sum + (s.capital_usd || 0), 0);
  const totalPnl = strategies.reduce((sum, s) => sum + (s.total_pnl || 0), 0);
  const totalTrades = strategies.reduce(
    (sum, s) => sum + s.trades_won + s.trades_lost,
    0,
  );
  const totalOpen = strategies.reduce((sum, s) => sum + (s.positions_open || 0), 0);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Global summary */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Capital Total', value: `$${totalCapital.toFixed(2)}` },
          {
            label: 'P&L Total',
            value: `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`,
            color: totalPnl > 0 ? 'text-emerald-400' : totalPnl < 0 ? 'text-red-400' : 'text-white',
          },
          { label: 'Trades Totales', value: totalTrades },
          { label: 'Posiciones Abiertas', value: totalOpen },
        ].map((m) => (
          <div
            key={m.label}
            className="bg-gray-900/50 rounded-xl border border-gray-700/30 p-4 text-center"
          >
            <p className="text-xs text-gray-500">{m.label}</p>
            <p className={`text-lg font-bold mt-1 ${m.color || 'text-white'}`}>
              {m.value}
            </p>
          </div>
        ))}
      </div>

      {/* Strategy cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {strategies.map((strategy, i) => (
          <StrategyCard
            key={strategy.id}
            strategy={strategy}
            index={i}
            onClick={() => setSelectedStrategy(strategy.id)}
          />
        ))}
      </div>
    </motion.div>
  );
}
