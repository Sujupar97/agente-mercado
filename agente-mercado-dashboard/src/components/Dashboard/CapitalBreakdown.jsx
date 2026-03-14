import { motion } from 'framer-motion';
import {
  BanknotesIcon,
  ArrowTrendingDownIcon,
  LockClosedIcon,
  WalletIcon,
} from '@heroicons/react/24/outline';

export function CapitalBreakdown({ agentData }) {
  const initial = agentData?.initial_capital_usd || 50;
  const available = agentData?.capital_usd || 0;
  const inPositions = agentData?.capital_in_positions || 0;
  const totalPnl = agentData?.total_pnl || 0;
  const positionsOpen = agentData?.positions_open || 0;
  const won = agentData?.trades_won || 0;
  const lost = agentData?.trades_lost || 0;
  const totalTrades = won + lost;
  const cycleMinutes = agentData?.cycle_interval_minutes || 10;

  // Porcentaje visual de la barra
  const totalAccount = available + inPositions;
  const availablePct = totalAccount > 0 ? (available / initial) * 100 : 0;
  const inPositionsPct = totalAccount > 0 ? (inPositions / initial) * 100 : 0;
  const lostPct = totalPnl < 0 ? (Math.abs(totalPnl) / initial) * 100 : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.05 }}
      className="rounded-xl border border-blue-500/20 bg-gray-900/60 backdrop-blur-xl overflow-hidden"
    >
      <div className="px-6 py-4 border-b border-gray-700/50">
        <h2 className="text-lg font-semibold text-white">Donde esta tu dinero</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Desglose de tu capital de ${initial.toFixed(2)}
        </p>
      </div>

      <div className="p-5 space-y-5">
        {/* Barra visual */}
        <div className="space-y-2">
          <div className="flex h-4 rounded-full overflow-hidden bg-gray-800">
            {availablePct > 0 && (
              <div
                className="bg-blue-500 transition-all duration-500"
                style={{ width: `${Math.min(availablePct, 100)}%` }}
                title={`Disponible: $${available.toFixed(2)}`}
              />
            )}
            {inPositionsPct > 0 && (
              <div
                className="bg-violet-500 transition-all duration-500"
                style={{ width: `${Math.min(inPositionsPct, 100)}%` }}
                title={`En posiciones: $${inPositions.toFixed(2)}`}
              />
            )}
            {lostPct > 0 && (
              <div
                className="bg-red-500/40 transition-all duration-500"
                style={{ width: `${Math.min(lostPct, 100)}%` }}
                title={`Perdido: $${Math.abs(totalPnl).toFixed(2)}`}
              />
            )}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            <span className="flex items-center">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500 mr-1.5" />
              <span className="text-gray-400">Disponible</span>
            </span>
            {inPositionsPct > 0 && (
              <span className="flex items-center">
                <span className="w-2.5 h-2.5 rounded-full bg-violet-500 mr-1.5" />
                <span className="text-gray-400">En posiciones</span>
              </span>
            )}
            {lostPct > 0 && (
              <span className="flex items-center">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500/40 mr-1.5" />
                <span className="text-gray-400">Perdido</span>
              </span>
            )}
          </div>
        </div>

        {/* Detalle numerico */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/30">
            <div className="flex items-center space-x-2 mb-1.5">
              <BanknotesIcon className="w-4 h-4 text-gray-500" />
              <span className="text-xs text-gray-500">Capital Inicial</span>
            </div>
            <p className="text-lg font-bold text-white">${initial.toFixed(2)}</p>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/30">
            <div className="flex items-center space-x-2 mb-1.5">
              <WalletIcon className="w-4 h-4 text-blue-400" />
              <span className="text-xs text-gray-500">Disponible</span>
            </div>
            <p className="text-lg font-bold text-blue-400">${available.toFixed(2)}</p>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/30">
            <div className="flex items-center space-x-2 mb-1.5">
              <LockClosedIcon className="w-4 h-4 text-violet-400" />
              <span className="text-xs text-gray-500">En Posiciones</span>
            </div>
            <p className="text-lg font-bold text-violet-400">
              ${inPositions.toFixed(2)}
              {positionsOpen > 0 && (
                <span className="text-xs font-normal text-gray-500 ml-1">
                  ({positionsOpen} {positionsOpen === 1 ? 'abierta' : 'abiertas'})
                </span>
              )}
            </p>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/30">
            <div className="flex items-center space-x-2 mb-1.5">
              <ArrowTrendingDownIcon className={`w-4 h-4 ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`} />
              <span className="text-xs text-gray-500">Ganado / Perdido</span>
            </div>
            <p className={`text-lg font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}
            </p>
          </div>
        </div>

        {/* Explicacion en texto simple */}
        <div className="bg-gray-800/30 rounded-lg p-3.5 border border-gray-700/20">
          <p className="text-sm text-gray-300 leading-relaxed">
            {totalPnl < 0 && inPositions === 0 && (
              <>
                Empezaste con <span className="text-white font-semibold">${initial.toFixed(2)}</span>.
                {' '}Las operaciones cerradas perdieron un total de{' '}
                <span className="text-red-400 font-semibold">${Math.abs(totalPnl).toFixed(2)}</span>.
                {' '}Te quedan <span className="text-blue-400 font-semibold">${available.toFixed(2)}</span> disponibles.
                {totalTrades > 0 && (
                  <> De {totalTrades} operaciones: {won} ganadas, {lost} perdidas.</>
                )}
              </>
            )}
            {totalPnl < 0 && inPositions > 0 && (
              <>
                Empezaste con <span className="text-white font-semibold">${initial.toFixed(2)}</span>.
                {' '}Tienes <span className="text-violet-400 font-semibold">${inPositions.toFixed(2)}</span> invertidos en {positionsOpen} {positionsOpen === 1 ? 'posicion abierta' : 'posiciones abiertas'}.
                {' '}Las operaciones cerradas perdieron{' '}
                <span className="text-red-400 font-semibold">${Math.abs(totalPnl).toFixed(2)}</span>.
                {' '}Te quedan <span className="text-blue-400 font-semibold">${available.toFixed(2)}</span> libres.
              </>
            )}
            {totalPnl >= 0 && inPositions === 0 && (
              <>
                Empezaste con <span className="text-white font-semibold">${initial.toFixed(2)}</span>.
                {' '}Has ganado <span className="text-emerald-400 font-semibold">+${totalPnl.toFixed(2)}</span> en total.
                {' '}Tienes <span className="text-blue-400 font-semibold">${available.toFixed(2)}</span> disponibles.
              </>
            )}
            {totalPnl >= 0 && inPositions > 0 && (
              <>
                Empezaste con <span className="text-white font-semibold">${initial.toFixed(2)}</span>.
                {' '}Has ganado <span className="text-emerald-400 font-semibold">+${totalPnl.toFixed(2)}</span>.
                {' '}Tienes <span className="text-violet-400 font-semibold">${inPositions.toFixed(2)}</span> en {positionsOpen} posiciones abiertas
                {' '}y <span className="text-blue-400 font-semibold">${available.toFixed(2)}</span> libres.
              </>
            )}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            El agente revisa precios cada {cycleMinutes} minutos. Si una posicion llega a su objetivo (TP) o limite de perdida (SL), se cierra automaticamente.
          </p>
        </div>
      </div>
    </motion.div>
  );
}
