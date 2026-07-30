"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { getSession, logoutSession, type SessionUser } from "@/lib/api";

type AuthContextValue = {
  user: SessionUser | null;
  loading: boolean;
  error: "offline" | "expired" | null;
  refresh: () => Promise<boolean>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  error: null,
  refresh: async () => false,
  logout: async () => undefined,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"offline" | "expired" | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const session = await getSession();
      setUser(session.user);
      setError(session.authenticated ? null : "expired");
      return session.authenticated;
    } catch {
      setUser(null);
      setError(navigator.onLine ? "expired" : "offline");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!pathname.startsWith("/dashboard")) {
      return;
    }
    let active = true;
    void getSession()
      .then((session) => {
        if (!active) return;
        setUser(session.user);
        setError(session.authenticated ? null : "expired");
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
        setError(navigator.onLine ? "expired" : "offline");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [pathname]);
  useEffect(() => {
    const handleOffline = () => setError("offline");
    const handleOnline = () => void refresh();
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, [refresh]);

  const logout = useCallback(async () => {
    await logoutSession().catch(() => undefined);
    setUser(null);
    setError("expired");
  }, []);

  return <AuthContext.Provider value={{ user, loading, error, refresh, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
