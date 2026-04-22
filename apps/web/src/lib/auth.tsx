"use client";

import {
    createContext,
    useContext,
    useEffect,
    useState,
    useCallback,
    type ReactNode,
} from "react";
import { clearAuthToken, fetchMe, readAuthToken, writeAuthToken, type UserProfile } from "@/lib/api";

interface AuthContextValue {
    user: UserProfile | null;
    loading: boolean;
    login: (token: string) => Promise<boolean>;
    logout: () => void;
    refresh: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextValue>({
    user: null,
    loading: true,
    login: async () => false,
    logout: () => { },
    refresh: async () => false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<UserProfile | null>(null);
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        const token = readAuthToken();
        setLoading(true);

        if (!token) {
            setUser(null);
            setLoading(false);
            return false;
        }

        try {
            const me = await fetchMe();
            setUser(me);
            return true;
        } catch {
            clearAuthToken();
            setUser(null);
            return false;
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const login = useCallback(async (token: string) => {
        writeAuthToken(token);
        return refresh();
    }, [refresh]);

    const logout = useCallback(() => {
        clearAuthToken();
        setUser(null);
        setLoading(false);
    }, []);

    return (
        <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}
