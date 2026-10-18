import { clearStoredToken, getStoredToken } from './auth';

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function apiRequest(path, options = {}) {
  const token = getStoredToken();
  if (!token) throw new Error('AUTH_REQUIRED');

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('NETWORK_ERROR');
  }

  if (response.status === 401) {
    clearStoredToken();
    window.location.assign('/login');
    throw new Error('AUTH_REQUIRED');
  }
  if (!response.ok) throw new Error(`API_${response.status}`);
  if (response.status === 204) return null;
  return response.json();
}
