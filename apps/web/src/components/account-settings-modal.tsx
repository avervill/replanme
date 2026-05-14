"use client";

import { useEffect, useState } from "react";
import { fetchSubscriptionUsage, type SubscriptionUsageResponse } from "@/lib/api";
import type { UserProfile } from "@/lib/api";

type AccountSettingsModalProps = {
  user: UserProfile;
  onClose: () => void;
  onOpenOnboarding?: () => void;
};

const usageRows: Array<[keyof SubscriptionUsageResponse["usage"], string]> = [
  ["aiActions", "AI actions"],
  ["weeklyPlans", "Weekly plans"],
  ["imageImports", "Image imports"],
  ["voiceInputs", "Voice inputs"],
  ["monthlyPlans", "Monthly planning"],
  ["smartReschedules", "Smart rescheduling"],
  ["energySchedules", "Energy scheduling"],
  ["recurringPlans", "Recurring AI planning"],
];

function formatMetric(metric: { used: number; limit: number | null; allowed: boolean }): string {
  if (!metric.allowed) return "Pro only";
  if (metric.limit === null) return "Unlimited";
  return `${metric.used} / ${metric.limit} used this month`;
}

export function AccountSettingsModal({ user, onClose, onOpenOnboarding }: AccountSettingsModalProps) {
  const [usage, setUsage] = useState<SubscriptionUsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchSubscriptionUsage()
      .then((data) => {
        if (mounted) setUsage(data);
      })
      .catch((err: unknown) => {
        if (mounted) setError(err instanceof Error ? err.message : "Could not load usage.");
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="dashboard-modal-backdrop fixed inset-0 z-[150] flex items-center justify-center px-4 py-6">
      <div className="dashboard-modal w-full max-w-2xl rounded-[1.5rem] p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Account</p>
            <h2 className="mt-3 text-2xl font-semibold text-calm-text">Plan and usage</h2>
            <p className="mt-2 text-sm text-calm-muted">{user.email}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-[rgba(124,58,237,0.16)] px-4 py-2 text-sm font-semibold text-calm-text transition hover:bg-white/70"
          >
            Close
          </button>
        </div>

        <div className="mt-6 rounded-2xl border border-[rgba(124,58,237,0.16)] bg-white/60 px-4 py-3">
          <p className="text-sm font-semibold text-calm-text">
            Plan: {(usage?.plan ?? user.plan).toUpperCase()}
          </p>
          <p className="mt-1 text-sm text-calm-muted">
            Status: {usage?.subscriptionStatus ?? user.subscription_status}
          </p>
          <p className="mt-1 text-sm font-semibold text-calm-text">
            Planning credits: {usage?.planningCredits ?? user.planning_credits}
          </p>
        </div>

        {onOpenOnboarding && (
          <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-[rgba(20,184,166,0.18)] bg-[rgba(20,184,166,0.08)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-calm-text">Planning setup</p>
              <p className="mt-1 text-sm text-calm-muted">Revisit your role, planning pain, energy profile, and first-plan prompt.</p>
            </div>
            <button
              type="button"
              onClick={onOpenOnboarding}
              className="rounded-xl border border-[rgba(20,184,166,0.24)] bg-white/70 px-4 py-2 text-sm font-semibold text-calm-text transition hover:bg-white"
            >
              Reopen onboarding
            </button>
          </div>
        )}

        {error ? (
          <p className="mt-5 rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        ) : !usage ? (
          <p className="mt-6 text-sm text-calm-muted">Loading usage...</p>
        ) : (
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {usageRows.map(([key, label]) => (
              <div key={key} className="rounded-2xl border border-[rgba(124,58,237,0.12)] bg-white/50 px-4 py-3">
                <p className="text-sm font-semibold text-calm-text">{label}</p>
                <p className="mt-1 text-sm text-calm-muted">{formatMetric(usage.usage[key])}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
