"use client";

import type { PaywallPayload } from "@/lib/api";
import { UpgradeButton } from "@/components/upgrade-button";

type PaywallModalProps = {
  paywall: PaywallPayload | null;
  onClose: () => void;
};

function featureLabel(feature: string | null): string {
  if (!feature) return "AI planning";
  return feature
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function PaywallModal({ paywall, onClose }: PaywallModalProps) {
  if (!paywall) return null;

  const title = paywall.paywall?.title ?? "Not enough planning credits";
  const description = paywall.paywall?.description ?? paywall.upgradeMessage;
  const usageText =
    typeof paywall.requiredCredits === "number" && typeof paywall.availableCredits === "number"
      ? `${paywall.availableCredits} available · ${paywall.requiredCredits} needed`
      : typeof paywall.limit === "number" && typeof paywall.used === "number"
        ? `${paywall.used} / ${paywall.limit} used this month`
        : "Upgrade for 300 planning credits/month";

  return (
    <div className="dashboard-modal-backdrop fixed inset-0 z-[160] flex items-center justify-center px-4 py-6">
      <div className="dashboard-modal w-full max-w-md rounded-[1.5rem] p-6 shadow-xl">
        <p className="eyebrow">{featureLabel(paywall.feature)}</p>
        <h2 className="mt-3 text-2xl font-semibold text-calm-text">{title}</h2>
        <p className="mt-3 text-sm leading-7 text-calm-muted">{description}</p>
        <div className="mt-5 rounded-2xl border border-[rgba(124,58,237,0.16)] bg-white/60 px-4 py-3">
          <p className="text-sm font-semibold text-calm-text">{usageText}</p>
          <p className="mt-1 text-sm leading-6 text-calm-muted">Pro includes 300 planning credits every month.</p>
        </div>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-[rgba(124,58,237,0.16)] px-4 py-2 text-sm font-semibold text-calm-text transition hover:bg-white/70"
          >
            Maybe later
          </button>
          <UpgradeButton className="rounded-full bg-calm-primary px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800" />
        </div>
      </div>
    </div>
  );
}
