import { motion } from 'framer-motion';
import {
  CurrencyDollarIcon,
  ChartBarIcon,
  ArrowTrendingUpIcon,
  BoltIcon,
  SignalIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { InfoTooltip } from '../ui/InfoTooltip';

export function StatsCards({ agentData }) {
  const totalPnl = agentData?.total_pnl || 0;
  const netProfit = agentData?.net_profit || 0;
  const drawdown = agentData?.drawdown_pct || 0;

  const stats = [
    {
      title: 'Capital Disponible',
      tooltip: 'Dinero libre para abrir nuevas operaciones. El resto esta invertido en posiciones abiertas.',
      value: `$${agentData?.capital_usd?.toFixed(2) || '0.00'}`,
      subtitle: `Pico: $${agentData?.peak_capital_usd?.toFixed(2) || '0.00'}`,
      icon: CurrencyDollarIcon,
      color: 'text-blue-400',
      iconBg: 'bg-blue-500/10',
      borderColor: 'border-blue-500/20',
    },
    {
      title: 'Ganancia / Perdida',
      tooltip: 'Cuanto has ganado o perdido en total con todas las operaciones cerradas.',
      value: `$${totalPnl.toFixed(2)}`,
      subtitle: `Neto (- costos): $${netProfit.toFixed(2)}`,
      icon: ArrowTrendingUpIcon,
      color: totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400',
      iconBg: totalPnl >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10',
      borderColor: totalPnl >= 0 ? 'border-emerald-500/20' : 'border-red-500/20',
    },
    {
      title: 'Tasa de Acierto',
      tooltip: 'Porcentaje de operaciones que terminaron en ganancia. 50%+ es bueno.',
      value: `${agentData?.win_rate?.toFixed(1) || '0.0'}%`,
      subtitle: `Caida max: ${(drawdown * 100).toFixed(1)}%`,
      icon: ChartBarIcon,
      color: (agentData?.win_rate || 0) >= 50 ? 'text-emerald-400' : 'text-amber-400',
      iconBg: (agentData?.win_rate || 0) >= 50 ? 'bg-emerald-500/10' : 'bg-amber-500/10',
      borderColor: (agentData?.win_rate || 0) >= 50 ? 'border-emerald-500/20' : 'border-amber-500/20',
    },
    {
      title: 'Posiciones Abiertas',
      tooltip: 'Operaciones activas ahora mismo. Cada una tiene un objetivo de ganancia (TP) y un limite de perdida (SL).',
      value: agentData?.positions_open || 0,
      subtitle: `Total: ${agentData?.trades_executed_total || 0} operaciones`,
      icon: BoltIcon,
      color: 'text-violet-400',
      iconBg: 'bg-violet-500/10',
      borderColor: 'border-violet-500/20',
    },
    {
      title: 'Neto 7 Dias',
      tooltip: 'Ganancias menos costos (fees de trading + IA) de la ultima semana.',
      value: `$${agentData?.net_7d?.toFixed(2) || '0.00'}`,
      subtitle: `14 dias: $${agentData?.net_14d?.toFixed(2) || '0.00'}`,
      icon: SignalIcon,
      color: (agentData?.net_7d || 0) >= 0 ? 'text-emerald-400' : 'text-red-400',
      iconBg: (agentData?.net_7d || 0) >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10',
      borderColor: (agentData?.net_7d || 0) >= 0 ? 'border-emerald-500/20' : 'border-red-500/20',
    },
    {
      title: 'Uso de IA',
      tooltip: 'Cuantas consultas al modelo de IA se han usado hoy. Limite: 95 consultas por dia.',
      value: `${agentData?.llm_usage?.rpd || 0}/${agentData?.llm_usage?.rpd_limit || 95}`,
      subtitle: `Por minuto: ${agentData?.llm_usage?.rpm || 0}/${agentData?.llm_usage?.rpm_limit || 5}`,
      icon: ClockIcon,
      color: 'text-cyan-400',
      iconBg: 'bg-cyan-500/10',
      borderColor: 'border-cyan-500/20',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {stats.map((stat, i) => (
        <motion.div
          key={stat.title}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: i * 0.07 }}
        >
          <div className={`relative rounded-xl border ${stat.borderColor} bg-gray-900/60 backdrop-blur-xl p-5 transition-all duration-300 hover:bg-gray-800/60 hover:shadow-lg hover:shadow-blue-500/5`}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wider inline-flex items-center">
                  {stat.title}
                  <InfoTooltip text={stat.tooltip} />
                </p>
                <p className={`text-2xl font-bold mt-1 ${stat.color}`}>
                  {stat.value}
                </p>
                <p className="text-xs text-gray-500 mt-1">{stat.subtitle}</p>
              </div>
              <div className={`${stat.iconBg} rounded-lg p-2.5`}>
                <stat.icon className={`w-5 h-5 ${stat.color}`} />
              </div>
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
