"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { customerApiClient, CustomerApiError, CustomerPublic } from "@/lib/customer-api-client";

interface CustomerAuthContextValue {
  customer: CustomerPublic | null;
  isLoading: boolean;
  isSessionExpired: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearSessionExpired: () => void;
  refreshCustomer: () => Promise<void>;
}

const CustomerAuthContext = createContext<CustomerAuthContextValue | undefined>(undefined);

export function CustomerAuthProvider({ children }: { children: React.ReactNode }) {
  const [customer, setCustomer] = useState<CustomerPublic | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSessionExpired, setIsSessionExpired] = useState(false);
  const accessTokenRef = useRef<string | null>(null);

  const handleUnauthorized = useCallback(() => {
    accessTokenRef.current = null;
    setCustomer((current) => {
      if (current) setIsSessionExpired(true);
      return null;
    });
  }, []);

  useEffect(() => {
    customerApiClient.configureAuth(() => accessTokenRef.current, handleUnauthorized);
  }, [handleUnauthorized]);

  // Attempt a silent refresh on load -- the refresh token lives in an
  // HttpOnly cookie scoped to /api/v1/customer-auth, entirely separate from
  // the staff refresh cookie.
  useEffect(() => {
    (async () => {
      try {
        const refreshed = await customerApiClient.refresh();
        accessTokenRef.current = refreshed.access_token;
        const me = await customerApiClient.getMe();
        setCustomer(me);
      } catch {
        accessTokenRef.current = null;
        setCustomer(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await customerApiClient.login(email, password);
    accessTokenRef.current = result.access_token;
    setCustomer(result.customer);
    setIsSessionExpired(false);
  }, []);

  const logout = useCallback(async () => {
    try {
      await customerApiClient.logout();
    } catch (err) {
      if (!(err instanceof CustomerApiError)) throw err;
    } finally {
      accessTokenRef.current = null;
      setCustomer(null);
    }
  }, []);

  const refreshCustomer = useCallback(async () => {
    const me = await customerApiClient.getMe();
    setCustomer(me);
  }, []);

  const clearSessionExpired = useCallback(() => setIsSessionExpired(false), []);

  return (
    <CustomerAuthContext.Provider
      value={{ customer, isLoading, isSessionExpired, login, logout, clearSessionExpired, refreshCustomer }}
    >
      {children}
    </CustomerAuthContext.Provider>
  );
}

export function useCustomerAuth(): CustomerAuthContextValue {
  const ctx = useContext(CustomerAuthContext);
  if (!ctx) throw new Error("useCustomerAuth must be used within a CustomerAuthProvider");
  return ctx;
}
