/**
 * API Client - El "mesero" que habla con el backend
 *
 * Este archivo configura axios (una librería para hacer peticiones HTTP)
 * con funcionalidades automáticas como:
 * - Agregar el token JWT en cada petición
 * - Manejar errores 401 (cuando el token expira)
 */

import axios from 'axios';

// En desarrollo: Vite proxy redirige /api a localhost:8000
// En producción (Netlify): VITE_API_URL apunta al backend en Railway
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

// Crear instancia de axios con configuración base
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 segundos máximo por petición
  headers: {
    'Content-Type': 'application/json',
  },
});

// INTERCEPTOR DE PETICIONES
// Se ejecuta ANTES de cada petición para agregar el token JWT
apiClient.interceptors.request.use(
  (config) => {
    // Buscar el token guardado en localStorage (memoria del navegador)
    const token = localStorage.getItem('jwt_token');

    // Si existe un token, agregarlo al header Authorization
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => {
    // Si hay error antes de enviar la petición, rechazar
    return Promise.reject(error);
  }
);

// INTERCEPTOR DE RESPUESTAS
// Se ejecuta DESPUÉS de cada respuesta para manejar errores
apiClient.interceptors.response.use(
  (response) => {
    // Si la respuesta es exitosa (200, 201, etc.), retornarla
    return response;
  },
  (error) => {
    // Si la respuesta es 401 (Unauthorized), significa que:
    // - El token expiró, o
    // - No hay token, o
    // - El token es inválido
    if (error.response?.status === 401) {
      // Borrar el token inválido
      localStorage.removeItem('jwt_token');

      // Disparar un evento personalizado para que otros componentes sepan
      // que hubo un error de autenticación
      window.dispatchEvent(new Event('auth-error'));
    }

    // Rechazar el error para que el componente que llamó pueda manejarlo
    return Promise.reject(error);
  }
);

export default apiClient;
