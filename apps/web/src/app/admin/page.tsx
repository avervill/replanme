"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchAdminUsers, type AdminUserSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
    if (!loading && user && !user.is_admin) router.replace("/dashboard");
  }, [loading, router, user]);

  useEffect(() => {
    if (!user?.is_admin) return;
    fetchAdminUsers()
      .then(setUsers)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load admin users."));
  }, [user]);

  if (loading || !user?.is_admin) {
    return <main className="landing-page flex min-h-screen items-center justify-center">Loading...</main>;
  }

  return (
    <main className="landing-page min-h-screen px-4 py-8">
      <section className="mx-auto max-w-6xl rounded-[1.5rem] border border-[rgba(124,58,237,0.16)] bg-white/70 p-6 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="eyebrow">Admin</p>
            <h1 className="mt-2 text-3xl font-semibold text-calm-text">Users</h1>
          </div>
          <Link href="/dashboard" className="rounded-full border border-[rgba(124,58,237,0.16)] px-4 py-2 text-sm font-semibold">
            Dashboard
          </Link>
        </div>
        {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.14em] text-calm-muted">
              <tr>
                <th className="py-3">User</th>
                <th>Plan</th>
                <th>Credits</th>
                <th>Requests</th>
                <th>Used</th>
                <th>Google</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.id} className="border-t border-[rgba(124,58,237,0.12)]">
                  <td className="py-3">
                    <Link href={`/admin/users/${item.id}`} className="font-semibold text-calm-text hover:text-calm-primary">
                      {item.email}
                    </Link>
                    <p className="text-xs text-calm-muted">{item.name ?? "No name"}</p>
                  </td>
                  <td>{item.plan}</td>
                  <td>{item.planningCredits}</td>
                  <td>{item.totalPlanningRequests}</td>
                  <td>{item.totalCreditsUsed}</td>
                  <td>{item.hasGoogleCalendar ? "Connected" : "No"}</td>
                  <td>{new Date(item.createdAt).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
