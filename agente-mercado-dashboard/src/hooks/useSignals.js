/**
 * Hook: useSignals
 *
 * ¿Qué hace?
 * -----------
 * Este hook trae las SEÑALES generadas por el LLM (Gemini).
 * Las señales son las "ideas de trading" que el agente tuvo, incluyendo:
 * - Qué par/mercado analizó
 * - Si piensa que va a subir o bajar
 * - Qué tan seguro está (confidence)
 * - Por qué piensa eso (rationale)
 *
 * ¿Cómo funciona?
 * ---------------
 * 1. Trae las últimas señales del LLM
 * 2. Se actualiza cada 20 segundos (las señales no cambian tan rápido)
 * 3. Puedes especificar cuántas señales quieres ver
 *
 * ¿Cómo se usa?
 * -------------
 * En tu componente:
 *
 * // Ver últimas 50 señales (default)
 * const { data, isLoading } = useSignals();
 *
 * // Ver últimas 100 señales
 * const { data } = useSignals(100);
 *
 * // Acceder a las señales
 * data?.forEach(signal => {
 *   console.log(signal.market_id);
 *   console.log(signal.direction);      // "BUY_YES" o "BUY_NO"
 *   console.log(signal.confidence);     // 0.0 - 1.0
 *   console.log(signal.llm_response_summary);  // El razonamiento
 * });
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

export function useSignals(limit = 50) {
  return useQuery({
    // El queryKey incluye el limit para diferenciar queries
    queryKey: ['signals', limit],

    // La función que trae los datos
    queryFn: async () => {
      const response = await api.getSignals(limit);
      return response.data;
    },

    // Configuración de actualización
    refetchInterval: 20000,      // Actualizar cada 20 segundos
    refetchOnWindowFocus: true,
    staleTime: 15000,            // Los datos son "frescos" por 15 segundos

    // Configuración de reintentos
    retry: 2,
    retryDelay: 1000,
  });
}
