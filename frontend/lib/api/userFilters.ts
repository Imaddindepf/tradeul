/**
 * User Filters API Client
 * Cliente para CRUD de filtros de usuario del scanner
 */

import type { UserFilter, UserFilterCreate, UserFilterUpdate } from '@/lib/types/scannerFilters';
import { authFetchStandalone } from '@/hooks/useAuthFetch';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_BASE = '/api/v1/user/filters';

// ============================================================================
// Helper: Auth Fetch JSON
// ============================================================================

async function authFetchJson<T>(
  endpoint: string,
  getToken: () => Promise<string | null>,
  options: RequestInit = {}
): Promise<T> {
  const url = endpoint.startsWith('http') 
    ? endpoint 
    : `${API_BASE_URL}${endpoint}`;
  
  const response = await authFetchStandalone(url, getToken, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  
  // Si es DELETE (204 No Content) o respuesta vacía, no intentar parsear JSON
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }
  
  const text = await response.text();
  if (!text) {
    return undefined as T;
  }
  
  return JSON.parse(text);
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Obtiene todos los filtros del usuario
 */
export async function getUserFilters(getToken: () => Promise<string | null>): Promise<UserFilter[]> {
  return authFetchJson<UserFilter[]>(API_BASE, getToken);
}

/**
 * Obtiene un filtro específico por ID
 */
export async function getUserFilter(
  id: number,
  getToken: () => Promise<string | null>
): Promise<UserFilter> {
  return authFetchJson<UserFilter>(`${API_BASE}/${id}`, getToken);
}

/**
 * Crea un nuevo filtro
 */
export async function createUserFilter(
  filter: UserFilterCreate,
  getToken: () => Promise<string | null>
): Promise<UserFilter> {
  return authFetchJson<UserFilter>(API_BASE, getToken, {
    method: 'POST',
    body: JSON.stringify(filter),
  });
}

/**
 * Actualiza un filtro existente
 */
export async function updateUserFilter(
  id: number,
  filter: UserFilterUpdate,
  getToken: () => Promise<string | null>
): Promise<UserFilter> {
  return authFetchJson<UserFilter>(`${API_BASE}/${id}`, getToken, {
    method: 'PUT',
    body: JSON.stringify(filter),
  });
}

/**
 * Elimina un filtro
 */
export async function deleteUserFilter(
  id: number,
  getToken: () => Promise<string | null>
): Promise<void> {
  await authFetchJson<void>(`${API_BASE}/${id}`, getToken, {
    method: 'DELETE',
  });
}

