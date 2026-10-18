import { createContext, useContext, useEffect, useState } from 'react';
import { connectRealtime } from './realtime';

const AuthContext = createContext(null);
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function getStoredToken() {
  return sessionStorage.getItem('access_token') || localStorage.getItem('access_token');
}

export function clearStoredToken() {
  sessionStorage.removeItem('access_token');
  localStorage.removeItem('access_token');
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [realtimeStatus, setRealtimeStatus] = useState('unauthenticated');
  const [realtimeEvents, setRealtimeEvents] = useState([]);

  useEffect(() => {
    const controller = new AbortController();
    const token = getStoredToken();
    if (!token) {
      setChecking(false);
      return () => controller.abort();
    }

    fetch(`${API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('Session expired');
        return response.json();
      })
      .then(setUser)
      .catch((error) => {
        if (error.name !== 'AbortError') {
          clearStoredToken();
          setUser(null);
        }
      })
      .finally(() => setChecking(false));

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (checking) return undefined;
    const token = getStoredToken();
    if (!user || !token) {
      setRealtimeStatus('unauthenticated');
      setRealtimeEvents([]);
      return undefined;
    }
    return connectRealtime({
      token,
      onStatus: setRealtimeStatus,
      onEvent: (event) => setRealtimeEvents((current) => [event, ...current].slice(0, 50)),
    });
  }, [checking, user?.user_id]);

  async function login(username, password) {
    let response;
    try {
      response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Action-Source': 'WEB',
        },
        body: JSON.stringify({ username, password }),
      });
    } catch {
      throw new Error('server_error');
    }

    if (response.status === 401) throw new Error('invalid_credentials');
    if (!response.ok) throw new Error('server_error');

    let result;
    try {
      result = await response.json();
    } catch {
      throw new Error('server_error');
    }
    if (!result.access_token || !result.user) throw new Error('server_error');

    clearStoredToken();
    sessionStorage.setItem('access_token', result.access_token);
    setUser(result.user);
    return result.user;
  }

  async function logout() {
    const token = getStoredToken();
    if (token) {
      try {
        await fetch(`${API_URL}/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'X-Action-Source': 'WEB' },
        });
      } catch {
      } finally {
        clearStoredToken();
        setUser(null);
      }
    } else {
      setUser(null);
    }
  }

  return <AuthContext.Provider value={{ user, checking, login, logout, realtimeStatus, realtimeEvents }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}