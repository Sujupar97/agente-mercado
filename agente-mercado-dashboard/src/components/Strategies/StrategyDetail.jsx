import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowLeftIcon,
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  AcademicCapIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import {
  useStrategyTrades,
  useStrategyBitacora,
  useStrategyReports,
  useStrategyPerformance,
  useImprovementCycles,
  useImprovementRules,
} from '../../hooks/useStrategies';

function DetailTab({ label, icon: Icon, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
        active
          ? 'bg-blue-500/15 text-blue-400'
          : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
      }`}
    >
      <Icon className="w-3.5 h-3.5 mr-1" />
      {label}
    </button>
  );
}

function TradesSection({ strategyId }) {
  const { data: trades, isLoading } = useStrategyTrades(strategyId);

  if (isLoading) return <LoadingSpinner />;
  if (!trades?.length) return <EmptyState text="Sin trades todavia" />;

  return (
    <div className="space-y-2">
      {trades.map((t) => (
        <div
          key={t.id}
          className="bg-gray-900/50 rounded-xl border border-gray-700/30 p-3"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span
                className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                  t.direction === 'BUY'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
              >
                {t.direction}
              </span>
              <span className="text-sm font-medium text-white">{t.symbol}</span>
            </div>
            <div className="text-right">
              <span
                className={`text-sm font-bold ${
                  t.pnl > 0 ? 'text-emerald-400' : t.pnl < 0 ? 'text-red-400' : 'text-gray-400'
                }`}
              >
                {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(4)}` : '-'}
              </span>
            </div>
          </div>
          <div className="flex items-center justify-between mt-1.5 text-xs text-gray-500">
            <span>Size: ${t.size_usd?.toFixed(2)}</span>
            <span>
              {t.status === 'OPEN' ? (
                <span className="text-blue-400">Abierta</span>
              ) : (
                new Date(t.closed_at).toLocaleString('es', {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                })
              )}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function BitacoraSection({ strategyId }) {
  const { data: entries, isLoading } = useStrategyBitacora(strategyId);

  if (isLoading) return <LoadingSpinner />;
  if (!entries?.length) return <EmptyState text="Sin entradas de bitacora" />;

  return (
    <div className="space-y-3">
      {entries.map((b) => (
        <div
          key={b.id}
          className="bg-gray-900/50 rounded-xl border border-gray-700/30 p-4 space-y-2"
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span
                className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                  b.direction === 'BUY'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
              >
                {b.direction}
              </span>
              <span className="text-sm font-medium text-white">{b.symbol}</span>
            </div>
            <div className="text-right">
              {b.pnl != null && (
                <span
                  className={`text-sm font-bold ${
                    b.pnl > 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {b.pnl >= 0 ? '+' : ''}${b.pnl.toFixed(4)}
                </span>
              )}
              {b.exit_reason && (
                <span
                  className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                    b.exit_reason === 'TAKE_PROFIT'
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-red-500/15 text-red-400'
                  }`}
                >
                  {b.exit_reason === 'TAKE_PROFIT' ? 'TP' : 'SL'}
                </span>
              )}
            </div>
          </div>

          {/* Entry reasoning */}
          {b.entry_reasoning && (
            <div className="bg-gray-800/50 rounded-lg p-2.5">
              <p className="text-xs text-gray-400 font-medium mb-0.5">Razonamiento:</p>
              <p className="text-xs text-gray-300">{b.entry_reasoning}</p>
            </div>
          )}

          {/* Lesson */}
          {b.lesson && (
            <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-2.5">
              <p className="text-xs text-blue-400 font-medium mb-0.5">Leccion:</p>
              <p className="text-xs text-blue-200">{b.lesson}</p>
            </div>
          )}

          {/* Timing */}
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>
              {new Date(b.entry_time).toLocaleString('es', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
              })}
            </span>
            {b.hold_duration_minutes != null && (
              <span>{Math.round(b.hold_duration_minutes)} min</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportsSection({ strategyId }) {
  const { data: reports, isLoading } = useStrategyReports(strategyId);

  if (isLoading) return <LoadingSpinner />;
  if (!reports?.length) return <EmptyState text="Sin reportes de aprendizaje (se generan cada 15 trades cerrados)" />;

  return (
    <div className="space-y-4">
      {reports.map((r) => (
        <div
          key={r.id}
          className="bg-gray-900/50 rounded-xl border border-gray-700/30 p-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-bold text-white">
              Reporte #{r.report_number}
            </h4>
            <span className="text-xs text-gray-500">
              {r.trades_analyzed} trades analizados
            </span>
          </div>

          {r.analysis && (
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-xs text-gray-300 whitespace-pre-wrap">{r.analysis}</p>
            </div>
          )}

          {r.recommendations?.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 font-medium mb-1">Recomendaciones:</p>
              <ul className="space-y-1">
                {r.recommendations.map((rec, i) => (
                  <li key={i} className="text-xs text-gray-300 flex items-start">
                    <span className="text-blue-400 mr-1.5 mt-0.5">-</span>
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {r.stats_snapshot && (
            <div className="grid grid-cols-4 gap-2 pt-2 border-t border-gray-700/30">
              <div className="text-center">
                <p className="text-xs text-gray-500">WR</p>
                <p className="text-xs font-bold text-white">
                  {((r.stats_snapshot.win_rate || 0) * 100).toFixed(0)}%
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-gray-500">PF</p>
                <p className="text-xs font-bold text-white">
                  {(r.stats_snapshot.profit_factor || 0).toFixed(2)}
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-gray-500">Sortino</p>
                <p className="text-xs font-bold text-white">
                  {(r.stats_snapshot.sortino || 0).toFixed(2)}
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-gray-500">Trades</p>
                <p className="text-xs font-bold text-white">
                  {r.stats_snapshot.total_trades || 0}
                </p>
              </div>
            </div>
          )}

          <p className="text-xs text-gray-600">
            {new Date(r.created_at).toLocaleString('es')}
          </p>
        </div>
      ))}
    </div>
  );
}

function PerformanceSection({ strategyId }) {
  const { data: perf, isLoading } = useStrategyPerformance(strategyId);

  if (isLoading) return <LoadingSpinner />;
  if (!perf || !perf.data_sufficient) {
    return (
      <EmptyState
        text={`Datos insuficientes: ${perf?.total_trades || 0}/30 trades necesarios`}
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Global metrics */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Win Rate', value: `${(perf.win_rate * 100).toFixed(0)}%` },
          { label: 'Profit Factor', value: perf.profit_factor.toFixed(2) },
          { label: 'Sortino', value: perf.sortino_ratio.toFixed(2) },
          { label: 'Expectancy', value: `$${perf.expectancy.toFixed(4)}` },
        ].map((m) => (
          <div key={m.label} className="bg-gray-900/50 rounded-xl border border-gray-700/30 p-3 text-center">
            <p className="text-xs text-gray-500">{m.label}</p>
            <p className="text-sm font-bold text-white mt-0.5">{m.value}</p>
          </div>
        ))}
      </div>

      {/* Best/Worst symbols */}
      {perf.best_symbols?.length > 0 && (
        <div>
          <p className="text-xs text-gray-400 font-medium mb-2">Mejores Simbolos</p>
          <div className="space-y-1.5">
            {perf.best_symbols.map((s) => (
              <div key={s.symbol} className="flex items-center justify-between bg-gray-900/30 rounded-lg px-3 py-1.5">
                <span className="text-xs text-white font-medium">{s.symbol}</span>
                <div className="flex items-center space-x-3 text-xs">
                  <span className="text-gray-400">WR {(s.win_rate * 100).toFixed(0)}%</span>
                  <span className={s.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                    ${s.total_pnl.toFixed(4)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {perf.recommendations?.length > 0 && (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3">
          <p className="text-xs text-amber-400 font-medium mb-1.5">Recomendaciones</p>
          {perf.recommendations.map((r, i) => (
            <p key={i} className="text-xs text-gray-300 mb-1">- {r}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function RulesSection({ strategyId }) {
  const { data: rules, isLoading: loadingRules } = useImprovementRules(strategyId);
  const { data: cycles, isLoading: loadingCycles } = useImprovementCycles(strategyId);

  if (loadingRules || loadingCycles) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      {/* Active Rules */}
      <div>
        <h4 className="text-sm font-bold text-white mb-2">
          Reglas Permanentes ({rules?.length || 0})
        </h4>
        {!rules?.length ? (
          <EmptyState text="Sin reglas todavia (se generan cada 20 trades cerrados)" />
        ) : (
          <div className="space-y-2">
            {rules.map((r) => (
              <div
                key={r.id}
                className="bg-gray-900/50 rounded-xl border border-amber-500/20 p-3 space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-amber-400">
                    {r.pattern_name}
                  </span>
                  <span className="text-xs text-gray-500">
                    Ciclo #{r.cycle_number}
                  </span>
                </div>
                <p className="text-xs text-gray-300">{r.description}</p>
                <div className="flex items-center space-x-3 text-xs text-gray-500">
                  <span>Tipo: {r.rule_type}</span>
                  <span>WR antes: {(r.win_rate_before * 100).toFixed(0)}%</span>
                  <span>{r.trades_before_rule} trades</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Cycle History */}
      <div>
        <h4 className="text-sm font-bold text-white mb-2">
          Historial de Ciclos
        </h4>
        {!cycles?.length ? (
          <EmptyState text="Sin ciclos completados" />
        ) : (
          <div className="space-y-2">
            {cycles.map((c) => (
              <div
                key={c.id}
                className="bg-gray-900/50 rounded-xl border border-gray-700/30 p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-white">
                    Ciclo #{c.cycle_number}
                  </span>
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded ${
                      c.status === 'completed'
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : c.status === 'analyzing'
                        ? 'bg-amber-500/15 text-amber-400'
                        : 'bg-blue-500/15 text-blue-400'
                    }`}
                  >
                    {c.status === 'completed'
                      ? 'Completado'
                      : c.status === 'analyzing'
                      ? 'Analizando'
                      : `${c.trades_in_cycle} trades`}
                  </span>
                </div>
                {c.loss_pattern_identified && (
                  <p className="text-xs text-gray-400 mt-1.5">
                    {c.loss_pattern_identified}
                  </p>
                )}
                {c.completed_at && (
                  <p className="text-xs text-gray-600 mt-1">
                    {new Date(c.completed_at).toLocaleString('es', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="w-6 h-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
    </div>
  );
}

function EmptyState({ text }) {
  return (
    <div className="text-center py-8">
      <p className="text-sm text-gray-500">{text}</p>
    </div>
  );
}

export function StrategyDetail({ strategy, onBack }) {
  const [tab, setTab] = useState('bitacora');

  const pnl = strategy.total_pnl || 0;
  const totalTrades = strategy.trades_won + strategy.trades_lost;

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="space-y-4"
    >
      {/* Back + Header */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onBack}
          className="p-2 rounded-lg hover:bg-gray-800/50 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 text-gray-400" />
        </button>
        <div className="flex-1">
          <h2 className="text-lg font-bold text-white">{strategy.name}</h2>
          <p className="text-xs text-gray-400">{strategy.description}</p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: 'Capital', value: `$${strategy.capital_usd?.toFixed(2)}` },
          {
            label: 'P&L',
            value: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`,
            color: pnl > 0 ? 'text-emerald-400' : pnl < 0 ? 'text-red-400' : 'text-white',
          },
          { label: 'Win Rate', value: `${(strategy.win_rate * 100).toFixed(0)}%` },
          { label: 'Trades', value: totalTrades },
          { label: 'Abiertas', value: strategy.positions_open },
        ].map((m) => (
          <div key={m.label} className="bg-gray-900/50 rounded-xl border border-gray-700/30 p-3 text-center">
            <p className="text-xs text-gray-500">{m.label}</p>
            <p className={`text-sm font-bold mt-0.5 ${m.color || 'text-white'}`}>
              {m.value}
            </p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-900/30 rounded-xl p-1">
        <DetailTab label="Bitacora" icon={BookOpenIcon} active={tab === 'bitacora'} onClick={() => setTab('bitacora')} />
        <DetailTab label="Reglas" icon={ShieldCheckIcon} active={tab === 'rules'} onClick={() => setTab('rules')} />
        <DetailTab label="Reportes" icon={AcademicCapIcon} active={tab === 'reports'} onClick={() => setTab('reports')} />
        <DetailTab label="Trades" icon={ClipboardDocumentListIcon} active={tab === 'trades'} onClick={() => setTab('trades')} />
        <DetailTab label="Rendimiento" icon={ChartBarIcon} active={tab === 'performance'} onClick={() => setTab('performance')} />
      </div>

      {/* Content */}
      <div>
        {tab === 'bitacora' && <BitacoraSection strategyId={strategy.id} />}
        {tab === 'rules' && <RulesSection strategyId={strategy.id} />}
        {tab === 'reports' && <ReportsSection strategyId={strategy.id} />}
        {tab === 'trades' && <TradesSection strategyId={strategy.id} />}
        {tab === 'performance' && <PerformanceSection strategyId={strategy.id} />}
      </div>
    </motion.div>
  );
}
