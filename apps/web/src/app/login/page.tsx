"use client";

import { useEffect, useState } from "react";
import { getGoogleAuthUrl, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function LoginPage() {
    const { user, loading } = useAuth();
    const router = useRouter();
    const [authUrl, setAuthUrl] = useState<string | null>(null);
    const [authError, setAuthError] = useState<string | null>(null);

    useEffect(() => {
        if (!loading && user) {
            router.replace("/dashboard");
        }
    }, [user, loading, router]);

    useEffect(() => {
        getGoogleAuthUrl()
            .then((url) => {
                setAuthUrl(url);
                setAuthError(null);
            })
            .catch((error: unknown) => {
                setAuthUrl(null);
                if (error instanceof ApiError || error instanceof Error) {
                    setAuthError(error.message);
                    return;
                }
                setAuthError("Failed to load Google sign-in. Check the API configuration and try again.");
            });
    }, []);

    return (
        <main className="flex min-h-screen flex-col items-center justify-center px-4">
            <div className="glass-panel w-full max-w-md rounded-[2rem] p-10 text-center">
                <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-ink">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-white">
                        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                </div>

                <h1 className="display-font text-3xl font-semibold text-ink">
                    Welcome to Resched.me
                </h1>
                <p className="mt-3 text-slate-600">
                    Sign in with Google to connect your calendar and start planning with AI.
                </p>

                {authError && (
                    <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-900">
                        {authError}
                    </p>
                )}

                <a
                    href={authUrl ?? "#"}
                    className={`mt-8 inline-flex items-center gap-3 rounded-full px-6 py-3 text-sm font-semibold transition ${authUrl
                            ? "bg-ink text-white hover:bg-slate-800"
                            : "cursor-wait bg-slate-300 text-slate-500"
                        }`}
                    aria-disabled={!authUrl}
                >
                    <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
                        <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4" />
                        <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853" />
                        <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05" />
                        <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335" />
                    </svg>
                    Sign in with Google
                </a>

                <p className="mt-6 text-xs text-slate-500">
                    We only request calendar access — no data is stored beyond your profile and events.
                </p>
            </div>
        </main>
    );
}
