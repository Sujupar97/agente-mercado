/**
 * Hook: usePnLHistory
 *
 * ¿Qué hace?
 * -----------
 * Este hook trae el HISTORIAL DE GANANCIAS Y PÉRDIDAS (P&L) día por día.
 * Es perfecto para hacer gráficas que muestran:
 * - Cómo ha crecido (o bajado) tu capital con el tiempo
 * - Cuánto ganaste/perdiste cada día
 * - Cuántos trades hiciste cada día
 * - Cuánto gastaste en costos (fees, LLM) cada día
 *
 * ¿Cómo funciona?
 * ---------------
 * 1. Trae los datos históricos de los últimos X días
 * 2. Se actualiza cada 60 segundos (el historial no cambia tan rápido)
 * 3. Los datos vienen ordenados por fecha
 *
 * ¿Cómo se usa?
 * -------------
 * En tu componente:
 *
 * // Ver últimos 30 días (default)
 * const { data, isLoading } = usePnLHistory();
 *
 * // Ver últimos 7 días
 * const { data } = usePnLHistory(7);
 *
 * // Acceder a los datos para una gráfica
 * data?.history.forEach(day => {
 *   console.log(day.date);          // "2026-03-01"
 *   console.log(day.capital);       // $350.25
 *   console.log(day.pnl);           // $12.50 (ganancias/pérdidas del día)
 *   console.log(day.costs);         // $0.50 (costos del día)
 *   console.log(day.net);           // $12.00 (pnl - costs)
 *   console.log(day.trades_count);  // 3 trades ese día
 * });
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

export function usePnLHistory(days = 30) {
  return useQuery({
    // El queryKey incluye el número de días
    queryKey: ['pnlHistory', days],

    // La función que trae los datos
    queryFn: async () => {
      const response = await api.getPnLHistory(days);
      return response.data;
    },

    // Configuración de actualización
    refetchInterval: 60000,      // Actualizar cada 60 segundos (1 minuto)
    refetchOnWindowFocus: true,
    staleTime: 50000,            // Los datos son "frescos" por 50 segundos

    // Configuración de reintentos
    retry: 2,
    retryDelay: 2000,
  });
}
