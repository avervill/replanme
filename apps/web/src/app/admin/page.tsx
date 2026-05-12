"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  fetchAdminOverview,
  fetchAdminTimeseries,
  fetchAdminUsers,
  type AdminOverview,
  type AdminTimeseries,
  type AdminUserSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

type FilterValue = "all" | "yes" | "no";

const metricLabels: Array<[keyof AdminOverview, string]> = [
  ["totalUsers", "Total users"],
  ["newUsersToday", "New today"],
  ["newUsersLast7Days", "New 7 days"],
  ["activeUsersToday", "Active today"],
  ["activeUsersLast7Days", "Active 7 days"],
  ["totalPlanningRequests", "AI requests"],
  ["successfulPlanningRequests", "Successful"],
  ["failedPlanningRequests", "Failed"],
  ["totalCreditsUsed", "Credits used"],
  ["totalCreditsGranted", "Credits granted"],
  ["googleCalendarConnectedUsers", "Google connected"],
  ["paywallViews", "Paywall views"],
  ["upgradeClicks", "Upgrade clicks"],
];

function booleanParam(value: FilterValue): boolean | undefined {
  if (value === "yes") return true;
  if (value === "no") return false;
  return undefined;
}

function MiniBars({ rows, metric, label }: { rows: AdminTimeseries["days"]; metric: keyof AdminTimeseries["days"][number]; label: string }) {
  const max = Math.max(1, ...rows.map((row) => Number(row[metric]) || 0));
  return (
    <div className="rounded-2xl border border-[rgba(124,58,237,0.12)] bg-white/55 p-4">
      <h3 className="text-sm font-semibold text-calm-text">{label}</h3>
      <div className="mt-4 space-y-2">
        {rows.slice(-14).map((row) => {
          const value = Number(row[metric]) || 0;
          return (
            <div key={`${String(metric)}-${row.date}`} className="grid grid-cols-[5.5rem_1fr_2.5rem] items-center gap-3 text-xs">
              <span className="text-calm-muted">{row.date.slice(5)}</span>
              <span className="h-2 overflow-hidden rounded-full bg-[rgba(124,58,237,0.1)]">
                <span className="block h-full rounded-full bg-calm-primary" style={{ width: `${Math.max(4, (value / max) * 100)}%` }} />
              </span>
              <strong className="text-right text-calm-text">{value}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const { user, loading, refresh } = useAuth();
  const router = useRouter();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [timeseries, setTimeseries] = useState<AdminTimeseries | null>(null);
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"createdAt" | "credits" | "email">("createdAt");
  const [adminFilter, setAdminFilter] = useState<FilterValue>("all");
  const [googleFilter, setGoogleFilter] = useState<FilterValue>("all");
  const [activeFilter, setActiveFilter] = useState<FilterValue>("all");
  const [error, setError] = useState<string | null>(null);
  const [accessRefreshAttempted, setAccessRefreshAttempted] = useState(false);
  const pageSize = 25;

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

  useEffect(() => {
    if (!user?.is_admin) return;
    Promise.all([fetchAdminOverview(), fetchAdminTimeseries("30d")])
      .then(([overviewData, seriesData]) => {
        setOverview(overviewData);
        setTimeseries(seriesData);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load admin analytics."));
  }, [user]);

  useEffect(() => {
    if (!user?.is_admin) return;
    fetchAdminUsers({
      page,
      pageSize,
      search,
      sort,
      admin: booleanParam(adminFilter),
      googleConnected: booleanParam(googleFilter),
      active: booleanParam(activeFilter),
    })
      .then((data) => {
        setUsers(data.items);
        setTotalUsers(data.total);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load admin users."));
  }, [activeFilter, adminFilter, googleFilter, page, search, sort, user]);

  const pageCount = useMemo(() => Math.max(1, Math.ceil(totalUsers / pageSize)), [totalUsers]);

  if (loading || !user?.is_admin) {
    return <main className="landing-page flex min-h-screen items-center justify-center">Loading...</main>;
  }

  return (
    <main className="landing-page min-h-screen px-4 py-8">
      <section className="mx-auto max-w-7xl rounded-[1.5rem] border border-[rgba(124,58,237,0.16)] bg-white/70 p-6 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="eyebrow">Admin</p>
            <h1 className="mt-2 text-3xl font-semibold text-calm-text">Analytics and users</h1>
          </div>
          <Link href="/dashboard" className="rounded-full border border-[rgba(124,58,237,0.16)] px-4 py-2 text-sm font-semibold">
            Dashboard
          </Link>
        </div>

        {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

        {overview && (
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {metricLabels.map(([key, label]) => (
              <div key={key} className="rounded-2xl border border-[rgba(124,58,237,0.12)] bg-white/60 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-calm-muted">{label}</p>
                <p className="mt-2 text-2xl font-semibold text-calm-text">{overview[key]}</p>
              </div>
            ))}
          </div>
        )}

        {timeseries && (
          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <MiniBars rows={timeseries.days} metric="signups" label="Daily signups" />
            <MiniBars rows={timeseries.days} metric="planningRequests" label="Daily AI requests" />
            <MiniBars rows={timeseries.days} metric="creditsUsed" label="Daily credits used" />
          </div>
        )}

        <div className="mt-8 rounded-2xl border border-[rgba(124,58,237,0.12)] bg-white/50 p-4">
          <div className="grid gap-3 lg:grid-cols-[1fr_160px_140px_140px_140px]">
            <input
              value={search}
              onChange={(event) => {
                setPage(1);
                setSearch(event.target.value);
              }}
              placeholder="Search by email or name"
              className="rounded-xl border border-[rgba(124,58,237,0.16)] bg-white px-3 py-2 text-sm"
            />
            <select value={sort} onChange={(event) => setSort(event.target.value as "createdAt" | "credits" | "email")} className="rounded-xl border bg-white px-3 py-2 text-sm">
              <option value="createdAt">Newest</option>
              <option value="credits">Credits</option>
              <option value="email">Email</option>
            </select>
            <select value={adminFilter} onChange={(event) => setAdminFilter(event.target.value as FilterValue)} className="rounded-xl border bg-white px-3 py-2 text-sm">
              <option value="all">All roles</option>
              <option value="yes">Admins</option>
              <option value="no">Users</option>
            </select>
            <select value={googleFilter} onChange={(event) => setGoogleFilter(event.target.value as FilterValue)} className="rounded-xl border bg-white px-3 py-2 text-sm">
              <option value="all">Google any</option>
              <option value="yes">Google yes</option>
              <option value="no">Google no</option>
            </select>
            <select value={activeFilter} onChange={(event) => setActiveFilter(event.target.value as FilterValue)} className="rounded-xl border bg-white px-3 py-2 text-sm">
              <option value="all">Activity any</option>
              <option value="yes">Active</option>
              <option value="no">Inactive</option>
            </select>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1040px] text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.14em] text-calm-muted">
              <tr>
                <th className="py-3">User</th>
                <th>Plan</th>
                <th>Credits</th>
                <th>Requests</th>
                <th>Used</th>
                <th>Google</th>
                <th>Active</th>
                <th>Role</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.id} className="border-t border-[rgba(124,58,237,0.12)]">
                  <td className="py-3">
                    <Link href={`/admin/users/${item.id}`} className="font-semibold text-calm-text hover:text-calm-primary">
                      {item.email}
                    </Link>
                    <p className="text-xs text-calm-muted">{item.name ?? item.id}</p>
                  </td>
                  <td>{item.plan}</td>
                  <td>{item.planningCredits}</td>
                  <td>{item.totalPlanningRequests}</td>
                  <td>{item.totalCreditsUsed}</td>
                  <td>{item.hasGoogleCalendar ? "Yes" : "No"}</td>
                  <td>{item.active ? "Yes" : "No"}</td>
                  <td>{item.isAdmin ? "Admin" : "User"}</td>
                  <td>{new Date(item.createdAt).toLocaleDateString()}</td>
                  <td>
                    <Link href={`/admin/users/${item.id}`} className="font-semibold text-calm-primary">
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-5 flex items-center justify-between text-sm">
          <span className="text-calm-muted">
            Page {page} of {pageCount} - {totalUsers} users
          </span>
          <div className="flex gap-2">
            <button type="button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} className="rounded-xl border px-3 py-2 disabled:opacity-40">
              Previous
            </button>
            <button type="button" disabled={page >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))} className="rounded-xl border px-3 py-2 disabled:opacity-40">
              Next
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
