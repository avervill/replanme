"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  adminAdjustCredits,
  adminGrantCredits,
  adminSetPlan,
  fetchAdminUser,
  type AdminUserDetail,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

function transactionLabel(type: string, normalizedType?: string): string {
  return (normalizedType || type).replace(/_/g, " ");
}

export default function AdminUserPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = use(params);
  const { user, loading, refresh } = useAuth();
  const router = useRouter();
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [amount, setAmount] = useState("5");
  const [reason, setReason] = useState("Manual admin credit change");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [accessRefreshAttempted, setAccessRefreshAttempted] = useState(false);

  const reload = () => {
    fetchAdminUser(userId)
      .then((data) => {
        setDetail(data);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load user."));
  };

  useEffect(() => {
    if (user?.is_admin) reload();
  }, [user?.is_admin, userId]);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (user.is_admin) return;
    if (!accessRefreshAttempted) {
      setAccessRefreshAttempted(true);
      void refresh();
      return;
    }
    router.replace("/dashboard");
  }, [accessRefreshAttempted, loading, refresh, router, user]);

  if (loading || !user?.is_admin) {
    return <main className="landing-page flex min-h-screen items-center justify-center">Loading...</main>;
  }

  const parsedAmount = Number.parseInt(amount, 10);
  const reasonValid = reason.trim().length > 0;

  return (
    <main className="landing-page min-h-screen px-4 py-8">
      <section className="mx-auto max-w-6xl rounded-[1.5rem] border border-[rgba(124,58,237,0.16)] bg-white/70 p-6 shadow-xl">
        <Link href="/admin" className="text-sm font-semibold text-calm-muted">Back to admin</Link>
        {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        {success && <p className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p>}
        {!detail ? (
          <p className="mt-6 text-sm text-calm-muted">Loading user...</p>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="eyebrow">Admin user</p>
                <h1 className="mt-2 text-3xl font-semibold text-calm-text">{detail.email}</h1>
                <p className="mt-2 text-sm text-calm-muted">
                  {detail.plan} / {detail.planningCredits} credits / {detail.hasGoogleCalendar ? "Google connected" : "No Google connection"} / {detail.active ? "Active" : "Inactive"}
                </p>
              </div>
              <select
                value={detail.plan}
                onChange={async (event) => {
                  await adminSetPlan(userId, event.target.value as "free" | "pro" | "admin");
                  setSuccess("Plan updated.");
                  reload();
                }}
                className="rounded-xl border border-[rgba(124,58,237,0.16)] bg-white px-3 py-2 text-sm font-semibold"
              >
                <option value="free">free</option>
                <option value="pro">pro</option>
                <option value="admin">admin</option>
              </select>
            </div>

            <div className="mt-6 rounded-2xl border border-[rgba(124,58,237,0.12)] bg-white/55 p-4">
              <h2 className="text-lg font-semibold text-calm-text">Credit management</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-[120px_1fr_auto_auto]">
                <input value={amount} onChange={(event) => setAmount(event.target.value)} className="rounded-xl border px-3 py-2" />
                <input value={reason} onChange={(event) => setReason(event.target.value)} className="rounded-xl border px-3 py-2" />
                <button
                  type="button"
                  disabled={!Number.isInteger(parsedAmount) || parsedAmount <= 0 || !reasonValid}
                  onClick={async () => {
                    await adminGrantCredits(userId, parsedAmount, reason);
                    setSuccess("Credits granted.");
                    reload();
                  }}
                  className="rounded-xl bg-calm-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Grant
                </button>
                <button
                  type="button"
                  disabled={!Number.isInteger(parsedAmount) || parsedAmount === 0 || !reasonValid}
                  onClick={async () => {
                    await adminAdjustCredits(userId, parsedAmount, reason);
                    setSuccess("Credits adjusted.");
                    reload();
                  }}
                  className="rounded-xl border border-[rgba(124,58,237,0.16)] px-4 py-2 text-sm font-semibold disabled:opacity-50"
                >
                  Adjust
                </button>
              </div>
            </div>

            <div className="mt-8 grid gap-6 lg:grid-cols-2">
              <div>
                <h2 className="text-lg font-semibold text-calm-text">Credit transactions</h2>
                <div className="mt-3 space-y-2">
                  {detail.creditTransactions.map((tx) => (
                    <div key={tx.id} className="rounded-xl border border-[rgba(124,58,237,0.12)] bg-white/60 px-4 py-3 text-sm">
                      <p className="font-semibold capitalize">{transactionLabel(tx.type, tx.normalizedType)}: {tx.amount > 0 ? "+" : ""}{tx.amount}</p>
                      <p className="text-calm-muted">{tx.balanceBefore} {"->"} {tx.balanceAfter} / {tx.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h2 className="text-lg font-semibold text-calm-text">Planning requests</h2>
                <div className="mt-3 space-y-2">
                  {detail.planningRequests.map((request) => (
                    <div key={request.id} className="rounded-xl border border-[rgba(124,58,237,0.12)] bg-white/60 px-4 py-3 text-sm">
                      <p className="font-semibold">{request.status} / {request.feature ?? request.intent ?? "unknown"}</p>
                      <p className="text-calm-muted">{request.creditsUsed}/{request.estimatedCredits} credits / {request.prompt ?? "No prompt"}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-8">
              <h2 className="text-lg font-semibold text-calm-text">Recent analytics events</h2>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {(detail.analyticsEvents ?? []).map((event) => (
                  <div key={event.id} className="rounded-xl border border-[rgba(124,58,237,0.12)] bg-white/60 px-4 py-3 text-sm">
                    <p className="font-semibold">{event.eventName}</p>
                    <p className="text-calm-muted">{event.feature ?? "general"} / {new Date(event.createdAt).toLocaleString()}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
