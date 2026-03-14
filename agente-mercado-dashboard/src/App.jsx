import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  SignalIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
  InformationCircleIcon,
  ChartBarIcon,
  AcademicCapIcon,
  BeakerIcon,
} from '@heroicons/react/24/outline';

import { SimulationControls } from './components/SimulationControls';
import { CapitalBreakdown } from './components/Dashboard/CapitalBreakdown';
import { StatsCards } from './components/Dashboard/StatsCards';
import { TradesTable } from './components/Dashboard/TradesTable';
import { SignalsPanel } from './components/Dashboard/SignalsPanel';
import { PnLChart } from './components/Dashboard/PnLChart';
import { LearningPage } from './components/Learning/LearningPage';
import { StrategiesPage } from './components/Strategies/StrategiesPage';
import { useAgentData } from './hooks/useAgentData';
import { usePnLHistory } from './hooks/usePnLHistory';
import { useSignals } from './hooks/useSignals';
import { useTrades } from './hooks/useTrades';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 2,
    },
  },
});

function SurvivalBanner({ status, reason }) {
  if (!status || status === 'CONTINUE') return null;

  const config = {
    WARNING: {
      icon: ExclamationTriangleIcon,
      bg: 'bg-amber-500/10 border-amber-500/30',
      text: 'text-amber-300',
    },
    SIMULATION: {
      icon: InformationCircleIcon,
      bg: 'bg-blue-500/10 border-blue-500/30',
      text: 'text-blue-300',
    },
    SHUTDOWN: {
      icon: XCircleIcon,
      bg: 'bg-red-500/10 border-red-500/30',
      text: 'text-red-300',
    },
  };

  const c = config[status] || config.SIMULATION;
  const Icon = c.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl border ${c.bg} p-4`}
    >
      <div className="flex items-center space-x-3">
        <Icon className={`w-5 h-5 ${c.text} flex-shrink-0`} />
        <div>
          <p className={`text-sm font-semibold ${c.text}`}>{status}</p>
          <p className="text-xs text-gray-400 mt-0.5">{reason}</p>
        </div>
      </div>
    </motion.div>
  );
}

function DashboardContent() {
  const [needsAuth, setNeedsAuth] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');

  const { data: agentData, isLoading: loadingAgent, error: agentError, refetch: refetchAgent } = useAgentData();
  const { data: pnlHistory, isLoading: loadingPnL } = usePnLHistory(30);
  const { data: trades, isLoading: loadingTrades, refetch: refetchTrades } = useTrades({ limit: 20 });
  const { data: signals, isLoading: loadingSignals, refetch: refetchSignals } = useSignals(20);

  const handleUpdate = () => {
    refetchAgent();
    refetchTrades();
    refetchSignals();
  };

  useEffect(() => {
    const handleAuthError = () => {
      if (agentData?.mode === 'LIVE') {
        setNeedsAuth(true);
      }
    };

    window.addEventListener('auth-error', handleAuthError);
    return () => window.removeEventListener('auth-error', handleAuthError);
  }, [agentData?.mode]);

  if (needsAuth && agentData?.mode === 'LIVE') {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="bg-gray-900/80 backdrop-blur-xl border border-gray-700/50 p-8 rounded-2xl shadow-2xl max-w-md w-full">
          <h2 className="text-2xl font-bold text-white mb-4">Login Requerido</h2>
          <p className="text-gray-400 mb-6 text-sm">
            El agente esta en modo LIVE. Necesitas autenticarte para continuar.
          </p>
          <button
            onClick={() => alert('Login no implementado aun')}
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 px-4 rounded-xl transition-colors"
          >
            Iniciar Sesion
          </button>
        </div>
      </div>
    );
  }

  if (loadingAgent) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-2 border-blue-500/20" />
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-blue-500 animate-spin" />
          </div>
          <p className="text-gray-400 text-sm">Conectando con el agente...</p>
        </div>
      </div>
    );
  }

  if (agentError) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-8 max-w-md text-center">
          <XCircleIcon className="w-12 h-12 text-red-400 mx-auto mb-3" />
          <h3 className="text-red-300 font-semibold text-lg mb-2">Error de Conexion</h3>
          <p className="text-gray-400 text-sm mb-4">
            No se pudo conectar con el backend en localhost:8000
          </p>
          <button
            onClick={() => window.location.reload()}
            className="bg-red-500/20 hover:bg-red-500/30 text-red-300 text-sm font-semibold py-2 px-6 rounded-xl border border-red-500/30 transition-colors"
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  const lastCycle = agentData?.last_cycle_at
    ? new Date(agentData.last_cycle_at).toLocaleString('es', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : 'Nunca';

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Ambient gradient orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-600/8 rounded-full blur-[120px]" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-600/8 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 left-1/2 w-80 h-80 bg-violet-600/5 rounded-full blur-[100px]" />
      </div>

      {/* Header */}
      <header className="sticky top-0 z-50 bg-gray-950/80 backdrop-blur-xl border-b border-gray-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/20">
                <SignalIcon className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-base font-bold text-white leading-tight">Agente de Trading</h1>
                <p className="text-xs text-gray-500">Ultimo ciclo: {lastCycle}</p>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div className="hidden sm:block text-right">
                <p className="text-xs text-gray-500">Capital</p>
                <p className="text-sm font-bold text-white">
                  ${agentData?.capital_usd?.toFixed(2) || '0.00'}
                </p>
              </div>

              <span
                className={`inline-flex items-center px-3 py-1 rounded-lg text-xs font-semibold ${
                  agentData?.mode === 'LIVE'
                    ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30'
                    : agentData?.mode === 'SIMULATION'
                    ? 'bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/30'
                    : agentData?.mode === 'SHUTDOWN'
                    ? 'bg-red-500/15 text-red-400 ring-1 ring-red-500/30'
                    : 'bg-gray-700 text-gray-400'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                  agentData?.mode === 'LIVE' ? 'bg-emerald-400 animate-pulse' :
                  agentData?.mode === 'SIMULATION' ? 'bg-blue-400 animate-pulse' :
                  'bg-gray-500'
                }`} />
                {agentData?.mode || 'UNKNOWN'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Tab Navigation */}
      <div className="sticky top-16 z-40 bg-gray-950/90 backdrop-blur-xl border-b border-gray-800/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-1 py-2">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'dashboard'
                  ? 'bg-blue-500/15 text-blue-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`}
            >
              <ChartBarIcon className="w-4 h-4 mr-1.5" />
              Dashboard
            </button>
            <button
              onClick={() => setActiveTab('strategies')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'strategies'
                  ? 'bg-blue-500/15 text-blue-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`}
            >
              <BeakerIcon className="w-4 h-4 mr-1.5" />
              Estrategias
            </button>
            <button
              onClick={() => setActiveTab('learning')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'learning'
                  ? 'bg-blue-500/15 text-blue-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`}
            >
              <AcademicCapIcon className="w-4 h-4 mr-1.5" />
              Aprendizaje
            </button>
          </nav>
        </div>
      </div>

      {/* Main Content */}
      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {activeTab === 'dashboard' && (
          <>
            {/* Survival Banner */}
            <SurvivalBanner
              status={agentData?.survival_status}
              reason={agentData?.survival_reason}
            />

            {/* Capital Breakdown - donde esta tu dinero */}
            <CapitalBreakdown agentData={agentData} />

            {/* Stats Cards */}
            <StatsCards agentData={agentData} />

            {/* Simulation Controls */}
            <SimulationControls agentMode={agentData?.mode} onUpdate={handleUpdate} />

            {/* P&L Chart */}
            <PnLChart pnlHistory={pnlHistory} loading={loadingPnL} />

            {/* Trades and Signals Grid */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <TradesTable trades={trades} loading={loadingTrades} />
              <SignalsPanel signals={signals} loading={loadingSignals} />
            </div>
          </>
        )}
        {activeTab === 'strategies' && <StrategiesPage />}
        {activeTab === 'learning' && <LearningPage />}
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-gray-800/50 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <p className="text-xs text-gray-600 text-center">
            Agente de Mercado v0.1.0 | Mercados analizados: {agentData?.markets_scanned_total?.toLocaleString() || 0}
          </p>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DashboardContent />
    </QueryClientProvider>
  );
}
