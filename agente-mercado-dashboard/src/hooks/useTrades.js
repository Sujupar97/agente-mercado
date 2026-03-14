/**
 * Hook: useTrades
 *
 * ¿Qué hace?
 * -----------
 * Este hook trae la lista de TRADES (operaciones) con filtros opcionales.
 * Puedes ver:
 * - Todos los trades
 * - Solo los que ganaron dinero
 * - Solo los que están abiertos
 * - Solo los últimos 50, 100, etc.
 *
 * ¿Cómo funciona?
 * ---------------
 * 1. Trae los trades según los filtros que le pases
 * 2. Se actualiza cada 15 segundos automáticamente
 * 3. Si cambias los filtros, vuelve a traer los datos
 *
 * ¿Cómo se usa?
 * -------------
 * En tu componente:
 *
 * // Ver todos los trades
 * const { data, isLoading } = useTrades();
 *
 * // Ver solo trades abiertos
 * const { data } = useTrades({ status: 'OPEN' });
 *
 * // Ver solo trades ganadores
 * const { data } = useTrades({ winner: true });
 *
 * // Combinar filtros
 * const { data } = useTrades({ status: 'CLOSED', winner: false, limit: 20 });
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

export function useTrades(filters = {}) {
  // Extraer los filtros con valores por defecto
  const {
    limit = 50,
    offset = 0,
    status = null,
    winner = null,
  } = filters;

  return useQuery({
    // El queryKey incluye los filtros para que React Query sepa
    // que son queries diferentes cuando cambian los filtros
    queryKey: ['trades', { limit, offset, status, winner }],

    // La función que trae los datos
    queryFn: async () => {
      // Construir el objeto de parámetros solo con los valores que existen
      const params = { limit, offset };
      if (status) params.status = status;
      if (winner !== null) params.winner = winner;

      const response = await api.getTrades(params);
      return response.data;
    },

    // Configuración de actualización
    refetchInterval: 15000,      // Actualizar cada 15 segundos
    refetchOnWindowFocus: true,
    staleTime: 12000,            // Los datos son "frescos" por 12 segundos

    // Configuración de reintentos
    retry: 2,
    retryDelay: 1000,
  });
}
