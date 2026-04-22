"use client";

import { useAuth } from "@/lib/auth";
import Link from "next/link";
import { useRouter } from "next/navigation";

export function Navbar() {
    const { user, logout } = useAuth();
    const router = useRouter();

    if (!user) return null;

    return (
        <nav className="sticky top-0 z-50 border-b border-black/5 bg-white/70 backdrop-blur-xl">
            <div className="mx-auto flex max-w-[1600px] items-center justify-between px-4 py-3 md:px-6 xl:px-8">
                <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="text-white">
                            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                    </div>
                    <span className="display-font text-lg font-semibold text-ink">
                        Resched.me
                    </span>
                </div>

                <div className="flex items-center gap-4">
                    <Link
                        href="/"
                        className="rounded-full border border-black/10 bg-white/80 px-4 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                    >
                        Landing
                    </Link>
                    {user.has_google_calendar && (
                        <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700">
                            Calendar connected
                        </span>
                    )}
                    <span className="text-sm text-slate-600">{user.email}</span>
                    <button
                        onClick={() => {
                            logout();
                            router.replace("/");
                        }}
                        className="rounded-full border border-black/10 bg-white/80 px-4 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                    >
                        Sign out
                    </button>
                </div>
            </div>
        </nav>
    );
}
