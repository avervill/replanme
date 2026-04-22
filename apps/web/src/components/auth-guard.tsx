"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

/**
 * Wrap a page with this component to require authentication.
 * Unauthenticated users are redirected to /login.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
    const { user, loading } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (!loading && !user) {
            router.replace("/login");
        }
    }, [user, loading, router]);

    if (loading) {
        return (
            <div className="flex min-h-screen items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-ink border-t-transparent" />
            </div>
        );
    }

    if (!user) return null;

    return <>{children}</>;
}
