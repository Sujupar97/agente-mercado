import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowPathIcon, PlusCircleIcon } from '@heroicons/react/24/outline';
import { api } from '../api/endpoints';

export function SimulationControls({ agentMode, onUpdate }) {
  const [amount, setAmount] = useState(100);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('');

  if (agentMode !== 'SIMULATION') {
    return null;
  }

  const showMessage = (text, type) => {
    setMessage(text);
    setMessageType(type);
    setTimeout(() => setMessage(''), 5000);
  };

  const handleAddCapital = async () => {
    if (amount <= 0) {
      showMessage('La cantidad debe ser mayor a 0', 'warning');
      return;
    }

    setLoading(true);
    try {
      const response = await api.addCapital(amount);
      showMessage(response.data.message, 'success');
      if (onUpdate) onUpdate();
    } catch (error) {
      showMessage(`Error: ${error.response?.data?.detail || error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleForceCycle = async () => {
    setLoading(true);
    showMessage('Ejecutando ciclo... esto puede tomar 2-3 minutos', 'info');

    try {
      await api.forceCycle();
      showMessage('Ciclo completado. Datos actualizandose...', 'success');
      setTimeout(() => {
        if (onUpdate) onUpdate();
      }, 3000);
    } catch (error) {
      showMessage(`Error: ${error.response?.data?.detail || error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className="rounded-xl border border-blue-500/20 bg-blue-950/20 backdrop-blur-xl p-5"
    >
      <div className="flex items-center space-x-2 mb-4">
        <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
        <h3 className="text-sm font-semibold text-blue-300 uppercase tracking-wider">
          Controles de Simulacion
        </h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Recargar Saldo */}
        <div className="bg-gray-900/40 rounded-lg p-4 border border-gray-700/30">
          <label className="block text-xs text-gray-400 mb-2 font-medium">
            Recargar Saldo (USD)
          </label>
          <div className="flex space-x-2">
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              min="1"
              className="flex-1 bg-gray-800/60 border border-gray-600/50 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/30 transition-colors"
              disabled={loading}
            />
            <button
              onClick={handleAddCapital}
              disabled={loading}
              className="inline-flex items-center bg-blue-600/80 hover:bg-blue-600 disabled:bg-gray-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all duration-200 hover:shadow-lg hover:shadow-blue-500/20"
            >
              <PlusCircleIcon className="w-4 h-4 mr-1.5" />
              {loading ? '...' : 'Recargar'}
            </button>
          </div>
        </div>

        {/* Forzar Ciclo */}
        <div className="bg-gray-900/40 rounded-lg p-4 border border-gray-700/30">
          <label className="block text-xs text-gray-400 mb-2 font-medium">
            Ejecutar Ciclo Manual
          </label>
          <button
            onClick={handleForceCycle}
            disabled={loading}
            className="w-full inline-flex items-center justify-center bg-indigo-600/80 hover:bg-indigo-600 disabled:bg-gray-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all duration-200 hover:shadow-lg hover:shadow-indigo-500/20"
          >
            <ArrowPathIcon className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Ejecutando...' : 'Forzar Ciclo Ahora'}
          </button>
          <p className="text-xs text-gray-500 mt-2">
            Ejecuta un ciclo de trading sin esperar 10 min
          </p>
        </div>
      </div>

      {/* Mensaje de feedback */}
      <AnimatePresence>
        {message && (
          <motion.div
            initial={{ opacity: 0, y: -10, height: 0 }}
            animate={{ opacity: 1, y: 0, height: 'auto' }}
            exit={{ opacity: 0, y: -10, height: 0 }}
            className={`mt-4 p-3 rounded-lg border text-sm ${
              messageType === 'success'
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                : messageType === 'error'
                ? 'bg-red-500/10 border-red-500/30 text-red-300'
                : messageType === 'warning'
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
            }`}
          >
            {message}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
