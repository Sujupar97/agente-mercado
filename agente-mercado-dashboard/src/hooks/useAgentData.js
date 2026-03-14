/**
 * Hook: useAgentData
 *
 * ¿Qué hace?
 * -----------
 * Este hook trae el ESTADO COMPLETO del agente cada 10 segundos.
 * Es como tener un "monitor en vivo" que te muestra:
 * - Cuánto capital tienes
 * - Cuánto has ganado o perdido (P&L)
 * - Si el agente está corriendo o pausado
 * - Cuántas posiciones tienes abiertas
 * - Etc.
 *
 * ¿Cómo funciona?
 * ---------------
 * 1. Cuando tu componente se monta (aparece en pantalla), empieza a traer datos
 * 2. Cada 10 segundos, vuelve a pedir los datos actualizados
 * 3. Guarda los datos en memoria para que no tengas que pedirlos cada vez
 * 4. Si hay un error, te lo dice
 *
 * ¿Cómo se usa?
 * -------------
 * En tu componente:
 *
 * const { data, isLoading, error, refetch } = useAgentData();
 *
 * - data: los datos del agente (capital, P&L, etc.)
 * - isLoading: true si está cargando, false si ya tiene datos
 * - error: si algo salió mal, aquí está el error
 * - refetch: función para forzar actualización manual
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

export function useAgentData() {
  return useQuery({
    // Nombre único para este query (como un ID)
    queryKey: ['agentStatus'],

    // La función que trae los datos
    queryFn: async () => {
      const response = await api.status();
      return response.data;
    },

    // Configuración de actualización automática
    refetchInterval: 10000,      // Refrescar cada 10 segundos (10000 ms)
    refetchOnWindowFocus: true,  // Refrescar cuando vuelvas a la pestaña
    staleTime: 8000,             // Los datos son "frescos" por 8 segundos

    // Configuración de reintentos si falla
    retry: 3,                    // Reintentar hasta 3 veces si falla
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}
