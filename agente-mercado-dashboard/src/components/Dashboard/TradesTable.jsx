import { motion, AnimatePresence } from 'framer-motion';
import { InfoTooltip } from '../ui/InfoTooltip';

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('es', { day: '2-digit', month: 'short' }) +
    ' ' + d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
}

export function TradesTable({ trades, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 bg-gray-700/50 rounded w-48" />
          <div className="h-4 bg-gray-700/30 rounded w-full" />
          <div className="h-4 bg-gray-700/30 rounded w-full" />
          <div className="h-4 bg-gray-700/30 rounded w-full" />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl overflow-hidden"
    >
      <div className="px-6 py-4 border-b border-gray-700/50">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Operaciones Recientes</h2>
          <span className="text-xs text-gray-500 bg-gray-800/50 px-2.5 py-1 rounded-full">
            {trades?.length || 0} operaciones
          </span>
        </div>
      </div>

      {!trades || trades.length === 0 ? (
        <div className="p-8 text-center">
          <p className="text-gray-500">No hay operaciones todavia</p>
          <p className="text-xs text-gray-600 mt-1">Ejecuta un ciclo para generar operaciones</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700/50">
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Fecha</th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Par</th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Dir.</th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Entrada</th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  <span className="inline-flex items-center">
                    Tamano
                    <InfoTooltip text="Cuanto dinero se invirtio en esta operacion. Por ejemplo, $3.00 significa que se usaron $3 de tu capital para esta operacion." />
                  </span>
                </th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Resultado</th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              <AnimatePresence>
                {trades.slice(0, 15).map((trade, idx) => {
                  const isClosed = trade.status === 'CLOSED';
                  const isWinner = isClosed && trade.pnl > 0;
                  const isLoser = isClosed && trade.pnl !== null && trade.pnl < 0;
                  const isNeutral = isClosed && trade.pnl !== null && trade.pnl === 0;

                  return (
                    <motion.tr
                      key={trade.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: idx * 0.03 }}
                      className={`transition-colors ${
                        isWinner ? 'hover:bg-emerald-500/5 bg-emerald-500/[0.02]' :
                        isLoser ? 'hover:bg-red-500/5 bg-red-500/[0.02]' :
                        'hover:bg-gray-800/40'
                      }`}
                    >
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span className="text-xs text-gray-500">{formatDate(trade.created_at)}</span>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span className="text-sm font-medium text-white">{trade.symbol}</span>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                            trade.direction === 'BUY'
                              ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30'
                              : 'bg-red-500/15 text-red-400 ring-1 ring-red-500/30'
                          }`}
                        >
                          {trade.direction === 'BUY' ? 'COMPRA' : 'VENTA'}
                        </span>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-300">
                        ${trade.entry_price?.toFixed(trade.entry_price >= 1 ? 2 : 6)}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-300">
                        ${trade.size_usd?.toFixed(2)}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        {trade.pnl !== null && trade.pnl !== undefined ? (
                          <span className={`text-sm font-semibold ${
                            trade.pnl > 0 ? 'text-emerald-400' :
                            trade.pnl < 0 ? 'text-red-400' :
                            'text-gray-500'
                          }`}>
                            {trade.pnl > 0 && '+'}${trade.pnl.toFixed(trade.pnl === 0 ? 2 : 4)}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-500">Esperando TP/SL</span>
                        )}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        {trade.status === 'OPEN' ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-500/15 text-blue-400">
                            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full mr-1.5 animate-pulse" />
                            Abierta
                          </span>
                        ) : isWinner ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/15 text-emerald-400">
                            Ganada
                          </span>
                        ) : isLoser ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-500/15 text-red-400">
                            Perdida
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-600/30 text-gray-400">
                            Cerrada
                          </span>
                        )}
                      </td>
                    </motion.tr>
                  );
                })}
              </AnimatePresence>
            </tbody>
          </table>
        </div>
      )}
    </motion.div>
  );
}
