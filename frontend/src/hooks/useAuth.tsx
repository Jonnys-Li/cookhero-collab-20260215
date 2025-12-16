import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { loginUser, registerUser } from '../services/api';
import type { AuthResponse, Credentials } from '../types';

interface AuthContextValue {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (credentials: Credentials) => Promise<void>;
  register: (credentials: Credentials) => Promise<void>;
  logout: () => void;
  updateProfile?: (data: { username?: string; occupation?: string; bio?: string }) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const TOKEN_KEY = 'cookhero_token';
const USERNAME_KEY = 'cookhero_username';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [username, setUsername] = useState<string | null>(() => localStorage.getItem(USERNAME_KEY));

  const persist = (data: AuthResponse) => {
    setToken(data.access_token);
    setUsername(data.username);
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USERNAME_KEY, data.username);
  };

  const updateProfile = async (data: { username?: string; occupation?: string; bio?: string }) => {
    if (!token) throw new Error('Not authenticated');
    const res = await (await import('../services/api')).updateProfile(data, token);
    // res is expected to be { username, occupation, bio }
    if (res.username) {
      setUsername(res.username);
      localStorage.setItem(USERNAME_KEY, res.username);
    }
  };

  const login = async (credentials: Credentials) => {
    const res = await loginUser(credentials);
    persist(res);
  };

  const register = async (credentials: Credentials) => {
    const res = await registerUser(credentials);
    persist(res);
  };

  const logout = () => {
    setToken(null);
    setUsername(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
  };

  const value = useMemo(() => ({
    token,
    username,
    isAuthenticated: Boolean(token),
    login,
    register,
    logout,
    updateProfile,
  }), [token, username]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
