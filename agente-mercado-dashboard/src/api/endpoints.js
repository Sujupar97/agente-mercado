/**
 * API Endpoints - Funciones para llamar a cada endpoint del backend
 *
 * En lugar de escribir axios.get('/api/v1/status') en cada componente,
 * centralizamos todas las llamadas aquí para mayor organización.
 */

import apiClient from './client';

export const api = {
  // ==========================================
  // AUTENTICACIÓN
  // ==========================================

  /**
   * Genera un token JWT para acceder a la API
   * @returns {Promise} Token JWT
   */
  generateToken: () => apiClient.post('/token'),

  // ==========================================
  // ESTADO Y SALUD DEL AGENTE
  // ==========================================

  /**
   * Health check - Verifica que el backend esté funcionando
   * @returns {Promise} {status, mode, uptime_seconds}
   */
  health: () => apiClient.get('/health'),

  /**
   * Estado completo del agente
   * @returns {Promise} Objeto con capital, P&L, posiciones, etc.
   */
  status: () => apiClient.get('/status'),

  // ==========================================
  // TRADES (OPERACIONES)
  // ==========================================

  /**
   * Obtiene lista de trades con filtros opcionales
   * @param {Object} params - Filtros: {limit, offset, status, winner}
   * @returns {Promise} Array de trades
   */
  getTrades: (params = {}) => apiClient.get('/trades', { params }),

  // ==========================================
  // POSICIONES ABIERTAS
  // ==========================================

  /**
   * Obtiene posiciones actualmente abiertas
   * @returns {Promise} Array de posiciones
   */
  getPositions: () => apiClient.get('/positions'),

  // ==========================================
  // SEÑALES DEL LLM
  // ==========================================

  /**
   * Obtiene señales generadas por el LLM
   * @param {Number} limit - Cantidad máxima de señales a retornar
   * @returns {Promise} Array de señales
   */
  getSignals: (limit = 50) => apiClient.get('/signals', { params: { limit } }),

  // ==========================================
  // P&L HISTÓRICO
  // ==========================================

  /**
   * Obtiene historial de P&L diario
   * @param {Number} days - Cantidad de días hacia atrás
   * @returns {Promise} Array de {date, capital, pnl, costs, net, trades_count}
   */
  getPnLHistory: (days = 30) =>
    apiClient.get('/stats/pnl-history', { params: { days } }),

  // ==========================================
  // USO DEL LLM
  // ==========================================

  /**
   * Obtiene estadísticas de uso del LLM (Gemini)
   * @returns {Promise} {rpm, rpd, límites, porcentajes}
   */
  getLLMUsage: () => apiClient.get('/llm-usage'),

  // ==========================================
  // CONTROL DEL AGENTE
  // ==========================================

  /**
   * Inicia el agente
   * @returns {Promise} Mensaje de confirmación
   */
  startAgent: () => apiClient.post('/agent/start'),

  /**
   * Pausa el agente
   * @returns {Promise} Mensaje de confirmación
   */
  stopAgent: () => apiClient.post('/agent/stop'),

  /**
   * Fuerza un ciclo manual del agente
   * @returns {Promise} Mensaje de confirmación
   */
  forceCycle: () => apiClient.post('/cycle'),

  // ==========================================
  // SIMULACIÓN
  // ==========================================

  /**
   * Añade capital simulado (solo en modo SIMULATION)
   * @param {Number} amount_usd - Cantidad en dólares a añadir
   * @returns {Promise} {success, message, new_capital}
   */
  addCapital: (amount_usd) =>
    apiClient.post('/simulation/add-capital', { amount_usd }),

  // ==========================================
  // CONFIGURACIÓN
  // ==========================================

  /**
   * Actualiza parámetros del agente en runtime
   * @param {Object} config - Parámetros a actualizar
   * @returns {Promise} Mensaje de confirmación
   */
  updateConfig: (config) => apiClient.put('/config', config),

  // ==========================================
  // APRENDIZAJE
  // ==========================================

  getPerformance: () => apiClient.get('/learning/performance'),
  getCalibration: () => apiClient.get('/learning/calibration'),
  getSymbolPerformance: () => apiClient.get('/learning/symbols'),
  getAdjustments: () => apiClient.get('/learning/adjustments'),
  getLearningLog: (limit = 50) =>
    apiClient.get('/learning/log', { params: { limit } }),

  // ==========================================
  // ESTRATEGIAS
  // ==========================================

  getStrategies: () => apiClient.get('/strategies'),
  getStrategyTrades: (strategyId, params = {}) =>
    apiClient.get(`/strategies/${strategyId}/trades`, { params }),
  getStrategyBitacora: (strategyId, limit = 50) =>
    apiClient.get(`/strategies/${strategyId}/bitacora`, { params: { limit } }),
  getStrategyReports: (strategyId, limit = 20) =>
    apiClient.get(`/strategies/${strategyId}/reports`, { params: { limit } }),
  getStrategyPerformance: (strategyId) =>
    apiClient.get(`/strategies/${strategyId}/performance`),

  // ==========================================
  // CICLO DE MEJORA
  // ==========================================

  getImprovementCycles: (strategyId, limit = 10) =>
    apiClient.get(`/strategies/${strategyId}/improvement-cycles`, { params: { limit } }),
  getImprovementRules: (strategyId) =>
    apiClient.get(`/strategies/${strategyId}/improvement-rules`),
};
