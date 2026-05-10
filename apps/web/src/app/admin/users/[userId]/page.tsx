"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import {
  adminAdjustCredits,
  adminGrantCredits,
  adminSetPlan,
  fetchAdminUser,
  type AdminUserDetail,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminUserPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = use(params);
  const { user, loading } = useAuth();
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [amount, setAmount] = useState("5");
  const [reason, setReason] = useState("Manual admin credit change");
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    fetchAdminUser(userId)
      .then(setDetail)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load user."));
  };

  useEffect(() => {
    if (user?.is_admin) reload();
  }, [user?.is_admin, userId]);

  if (loading || !user?.is_admin) {
    return <main className="landing-page flex min-h-screen items-center justify-center">Loading...</main>;
  }

  const parsedAmount = Number.parseInt(amount, 10);

  return (
    <main className="landing-page min-h-screen px-4 py-8">
      <section className="mx-auto max-w-6xl rounded-[1.5rem] border border-[rgba(124,58,237,0.16)] bg-white/70 p-6 shadow-xl">
        <Link href="/admin" className="text-sm font-semibold text-calm-muted">Back to users</Link>
        {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        {!detail ? (
          <p className="mt-6 text-sm text-calm-muted">Loading user...</p>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="eyebrow">Admin user</p>
                <h1 className="mt-2 text-3xl font-semibold text-calm-text">{detail.email}</h1>
                <p className="mt-2 text-sm text-calm-muted">
                  {detail.plan} · {detail.planningCredits} credits · {detail.hasGoogleCalendar ? "Google connected" : "No Google connection"}
                </p>
              </div>
              <select
                value={detail.plan}
                onChange={async (event) => {
                  await adminSetPlan(userId, event.target.value as "free" | "pro" | "admin");
                  reload();
                }}
                className="rounded-xl border border-[rgba(124,58,237,0.16)] bg-white px-3 py-2 text-sm font-semibold"
              >
                <option value="free">free</option>
                <option value="pro">pro</option>
                <option value="admin">admin</option>
              </select>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-[120px_1fr_auto_auto]">
              <input value={amount} onChange={(event) => setAmount(event.target.value)} className="rounded-xl border px-3 py-2" />
              <input value={reason} onChange={(event) => setReason(event.target.value)} className="rounded-xl border px-3 py-2" />
              <button
                type="button"
                onClick={async () => {
                  await adminGrantCredits(userId, parsedAmount, reason);
                  reload();
                }}
                className="rounded-xl bg-calm-primary px-4 py-2 text-sm font-semibold text-white"
              >
                Grant
              </button>
              <button
                type="button"
                onClick={async () => {
                  await adminAdjustCredits(userId, parsedAmount, reason);
                  reload();
                }}
                className="rounded-xl border border-[rgba(124,58,237,0.16)] px-4 py-2 text-sm font-semibold"
              >
                Adjust
              </button>
            </div>

            <div className="mt-8 grid gap-6 lg:grid-cols-2">
              <div>
                <h2 className="text-lg font-semibold text-calm-text">Credit transactions</h2>
                <div className="mt-3 space-y-2">
                  {detail.creditTransactions.map((tx) => (
                    <div key={tx.id} className="rounded-xl border border-[rgba(124,58,237,0.12)] bg-white/60 px-4 py-3 text-sm">
                      <p className="font-semibold">{tx.type}: {tx.amount > 0 ? "+" : ""}{tx.amount}</p>
                      <p className="text-calm-muted">{tx.balanceBefore} → {tx.balanceAfter} · {tx.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h2 className="text-lg font-semibold text-calm-text">Planning requests</h2>
                <div className="mt-3 space-y-2">
                  {detail.planningRequests.map((request) => (
                    <div key={request.id} className="rounded-xl border border-[rgba(124,58,237,0.12)] bg-white/60 px-4 py-3 text-sm">
                      <p className="font-semibold">{request.status} · {request.feature ?? "chat"}</p>
                      <p className="text-calm-muted">{request.creditsUsed}/{request.estimatedCredits} credits · {request.prompt ?? "No prompt"}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {detail.paywallEvents && detail.paywallEvents.length > 0 && (
              <div className="mt-8">
                <h2 className="text-lg font-semibold text-calm-text">Paywall events</h2>
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  {detail.paywallEvents.map((event) => (
                    <div key={event.id} className="rounded-xl border border-[rgba(124,58,237,0.12)] bg-white/60 px-4 py-3 text-sm">
                      <p className="font-semibold">{event.feature ?? "AI planning"}</p>
                      <p className="text-calm-muted">{new Date(event.createdAt).toLocaleString()}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}
