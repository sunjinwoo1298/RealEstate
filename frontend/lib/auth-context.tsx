"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { apiClient, ApiError, UserPublic } from "@/lib/api-client";

interface AuthContextValue {
  user: UserPublic | null;
  isLoading: boolean;
  isSessionExpired: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearSessionExpired: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSessionExpired, setIsSessionExpired] = useState(false);
  const accessTokenRef = useRef<string | null>(null);

  const handleUnauthorized = useCallback(() => {
    accessTokenRef.current = null;
    setUser((current) => {
      if (current) setIsSessionExpired(true);
      return null;
    });
  }, []);

  useEffect(() => {
    apiClient.configureAuth(() => accessTokenRef.current, handleUnauthorized);
  }, [handleUnauthorized]);

  // Attempt a silent refresh on load, since the refresh token lives in an
  // HttpOnly cookie that may still be valid across browser sessions.
  useEffect(() => {
    (async () => {
      try {
        const refreshed = await apiClient.refresh();
        accessTokenRef.current = refreshed.access_token;
        const me = await apiClient.getMe();
        setUser(me);
      } catch {
        accessTokenRef.current = null;
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await apiClient.login(email, password);
    accessTokenRef.current = result.access_token;
    setUser(result.user);
    setIsSessionExpired(false);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiClient.logout();
    } catch (err) {
      if (!(err instanceof ApiError)) throw err;
    } finally {
      accessTokenRef.current = null;
      setUser(null);
    }
  }, []);

  const clearSessionExpired = useCallback(() => setIsSessionExpired(false), []);

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isSessionExpired, login, logout, clearSessionExpired }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
