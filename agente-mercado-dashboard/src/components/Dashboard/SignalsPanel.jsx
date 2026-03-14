import { motion, AnimatePresence } from 'framer-motion';
import { useState } from 'react';
import { ChevronDownIcon } from '@heroicons/react/24/outline';
import { InfoTooltip } from '../ui/InfoTooltip';

function formatSignalDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('es', { day: '2-digit', month: 'short' }) +
    ' ' + d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
}

function SignalItem({ signal, index }) {
  const [isOpen, setIsOpen] = useState(false);
  const isBuy = signal.direction === 'BUY';
  const confidencePct = (signal.confidence * 100).toFixed(0);

  const confidenceLabel =
    signal.confidence >= 0.75 ? 'Muy segura' :
    signal.confidence >= 0.65 ? 'Segura' :
    signal.confidence >= 0.55 ? 'Moderada' : 'Baja';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
      className="border border-gray-700/50 rounded-lg overflow-hidden hover:border-gray-600/50 transition-colors"
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-3.5 text-left hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex items-center space-x-3 min-w-0">
          <span className="text-sm font-semibold text-white">{signal.symbol}</span>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
              isBuy
                ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30'
                : 'bg-red-500/15 text-red-400 ring-1 ring-red-500/30'
            }`}
          >
            {isBuy ? 'COMPRA' : 'VENTA'}
          </span>
          <span className="text-xs text-gray-600 hidden sm:inline">
            {formatSignalDate(signal.created_at)}
          </span>
        </div>

        <div className="flex items-center space-x-3 flex-shrink-0">
          <div className="text-right">
            <div className="flex items-center space-x-2">
              <span className="text-xs text-gray-500 hidden sm:inline">Confianza:</span>
              <div className="w-14 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    signal.confidence >= 0.7 ? 'bg-emerald-500' :
                    signal.confidence >= 0.5 ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${confidencePct}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 w-8">{confidencePct}%</span>
            </div>
          </div>
          <ChevronDownIcon
            className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          />
        </div>
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3">
              {/* Explicacion de confianza */}
              <div className="flex items-center space-x-2 text-xs">
                <span className={`px-2 py-0.5 rounded-full font-medium ${
                  signal.confidence >= 0.7 ? 'bg-emerald-500/15 text-emerald-400' :
                  signal.confidence >= 0.5 ? 'bg-amber-500/15 text-amber-400' :
                  'bg-red-500/15 text-red-400'
                }`}>
                  {confidenceLabel} ({confidencePct}%)
                </span>
                <span className="text-gray-500">
                  — La IA esta {confidencePct}% segura de esta idea
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-gray-800/50 rounded-lg p-2.5">
                  <p className="text-xs text-gray-500">Objetivo de Ganancia</p>
                  <p className="text-sm text-emerald-400 font-medium">
                    +{(signal.take_profit_pct * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-gray-600">Si sube, cierra aqui</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-2.5">
                  <p className="text-xs text-gray-500">Limite de Perdida</p>
                  <p className="text-sm text-red-400 font-medium">
                    -{(signal.stop_loss_pct * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-gray-600">Si baja, cierra aqui</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-2.5">
                  <p className="text-xs text-gray-500">Desviacion</p>
                  <p className="text-sm text-gray-300 font-medium">
                    {signal.deviation_pct > 0 ? '+' : ''}{(signal.deviation_pct * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-gray-600">vs precio justo</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-2.5">
                  <p className="text-xs text-gray-500">Modelo de IA</p>
                  <p className="text-sm text-gray-300 font-medium truncate">{signal.llm_model}</p>
                  <p className="text-xs text-gray-600">
                    {formatSignalDate(signal.created_at)}
                  </p>
                </div>
              </div>

              {signal.llm_response_summary && (
                <div className="bg-gray-800/30 rounded-lg p-3 border border-gray-700/30">
                  <p className="text-xs text-gray-500 mb-1 font-medium">Razonamiento de la IA</p>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    {signal.llm_response_summary}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function SignalsPanel({ signals, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 bg-gray-700/50 rounded w-56" />
          <div className="h-16 bg-gray-700/30 rounded w-full" />
          <div className="h-16 bg-gray-700/30 rounded w-full" />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
      className="rounded-xl border border-gray-700/50 bg-gray-900/60 backdrop-blur-xl overflow-hidden"
    >
      <div className="px-6 py-4 border-b border-gray-700/50">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white inline-flex items-center">
            Senales de la IA
            <InfoTooltip text="Ideas de trading que la IA genera al analizar precios, volumen y noticias. No todas se ejecutan — solo las que cumplen los criterios de riesgo. La barra de porcentaje muestra que tan segura esta la IA de cada idea (no es progreso hacia el TP/SL)." />
          </h2>
          <span className="text-xs text-gray-500 bg-gray-800/50 px-2.5 py-1 rounded-full">
            {signals?.length || 0} senales
          </span>
        </div>
        <p className="text-xs text-gray-600 mt-1">
          El % junto a cada senal indica que tan segura esta la IA de esa idea de trading
        </p>
      </div>

      <div className="p-4 space-y-2">
        {!signals || signals.length === 0 ? (
          <div className="p-4 text-center">
            <p className="text-gray-500">No hay senales todavia</p>
          </div>
        ) : (
          signals.slice(0, 10).map((signal, index) => (
            <SignalItem key={signal.id} signal={signal} index={index} />
          ))
        )}
      </div>
    </motion.div>
  );
}
