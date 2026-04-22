"use client";

import { useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Suspense } from "react";

function CallbackHandler() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const { login } = useAuth();
    const token = searchParams.get("token");

    useEffect(() => {
        let active = true;

        if (!token) {
            router.replace("/login");
            return;
        }

        const completeLogin = async () => {
            const isLoggedIn = await login(token);
            if (!active) {
                return;
            }
            router.replace(isLoggedIn ? "/dashboard" : "/login");
        };

        void completeLogin();

        return () => {
            active = false;
        };
    }, [token, login, router]);

    return (
        <div className="flex min-h-screen items-center justify-center">
            <div className="text-center">
                <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-ink border-t-transparent" />
                <p className="mt-4 text-sm text-slate-600">Signing you in…</p>
            </div>
        </div>
    );
}

export default function AuthCallbackPage() {
    return (
        <Suspense
            fallback={
                <div className="flex min-h-screen items-center justify-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-ink border-t-transparent" />
                </div>
            }
        >
            <CallbackHandler />
        </Suspense>
    );
}
