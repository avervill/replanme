"use client";

import { useState } from "react";
import {
  saveOnboarding,
  type OnboardingData,
  type OnboardingStatus,
  type UserProfile,
} from "@/lib/api";

type AccountSettingsModalProps = {
  user: UserProfile;
  onboardingStatus: OnboardingStatus | null;
  onClose: () => void;
  onPreferencesSaved?: (status: OnboardingStatus) => void;
};

type EnergyProfile = OnboardingData["energyProfile"];

const emptyEnergy: EnergyProfile = {
  peakFocusTime: [],
  lowEnergyTime: [],
  preferredWorkBlockLength: [],
  sleepPreference: [],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function fieldText(value: unknown): string {
  if (Array.isArray(value)) {
    return value.filter(Boolean).map(String).join("\n");
  }
  return typeof value === "string" ? value : "";
}

function listFromText(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function initialPreferences(status: OnboardingStatus | null, user: UserProfile) {
  const data = isRecord(status?.onboardingData) ? status.onboardingData : {};
  const energy = isRecord(data.energyProfile) ? data.energyProfile : emptyEnergy;

  return {
    role: fieldText(data.role) || "Just planning life",
    mainGoal: fieldText(data.mainGoal),
    planningPain: fieldText(data.planningPain),
    peakFocusTime: fieldText(energy.peakFocusTime),
    lowEnergyTime: fieldText(energy.lowEnergyTime),
    preferredWorkBlockLength: fieldText(energy.preferredWorkBlockLength),
    sleepPreference: fieldText(energy.sleepPreference),
    calendarIntent: fieldText(data.calendarIntent) || (user.has_google_calendar ? "Use my calendar to avoid conflicts" : "Let me generate drafts first"),
    firstPrompt: fieldText(data.firstPrompt) || "Plan my week around my goals, calendar, energy, and realistic focus blocks.",
  };
}

export function AccountSettingsModal({ user, onboardingStatus, onClose, onPreferencesSaved }: AccountSettingsModalProps) {
  const initial = initialPreferences(onboardingStatus, user);
  const [role, setRole] = useState(initial.role);
  const [mainGoal, setMainGoal] = useState(initial.mainGoal);
  const [planningPain, setPlanningPain] = useState(initial.planningPain);
  const [peakFocusTime, setPeakFocusTime] = useState(initial.peakFocusTime);
  const [lowEnergyTime, setLowEnergyTime] = useState(initial.lowEnergyTime);
  const [preferredWorkBlockLength, setPreferredWorkBlockLength] = useState(initial.preferredWorkBlockLength);
  const [sleepPreference, setSleepPreference] = useState(initial.sleepPreference);
  const [calendarIntent, setCalendarIntent] = useState(initial.calendarIntent);
  const [firstPrompt, setFirstPrompt] = useState(initial.firstPrompt);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = Boolean(role.trim() && calendarIntent.trim() && firstPrompt.trim());

  const submit = async () => {
    if (!canSave || saving) return;
    setSaving(true);
    setSaved(false);
    setError(null);

    const data: OnboardingData = {
      role: role.trim(),
      mainGoal: listFromText(mainGoal),
      planningPain: listFromText(planningPain),
      energyProfile: {
        peakFocusTime: listFromText(peakFocusTime),
        lowEnergyTime: listFromText(lowEnergyTime),
        preferredWorkBlockLength: listFromText(preferredWorkBlockLength),
        sleepPreference: listFromText(sleepPreference),
      },
      calendarIntent: calendarIntent.trim(),
      firstPrompt: firstPrompt.trim(),
    };

    try {
      const status = await saveOnboarding(data);
      onPreferencesSaved?.(status);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save preferences.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="dashboard-modal-backdrop fixed inset-0 z-[150] flex items-center justify-center px-4 py-6">
      <div className="dashboard-modal max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-[1.5rem] p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Account</p>
            <h2 className="mt-3 text-2xl font-semibold text-calm-text">Planning preferences</h2>
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

        {error ? (
          <p className="mt-5 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {saved ? (
          <p className="mt-5 rounded-xl border border-[rgba(20,184,166,0.22)] bg-[rgba(20,184,166,0.08)] px-4 py-3 text-sm font-semibold text-[var(--teal-deep)]">
            Preferences saved.
          </p>
        ) : null}

        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Role</span>
            <input
              value={role}
              onChange={(event) => setRole(event.target.value)}
              className="mt-2 w-full rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Calendar intent</span>
            <input
              value={calendarIntent}
              onChange={(event) => setCalendarIntent(event.target.value)}
              className="mt-2 w-full rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Main goals</span>
            <textarea
              value={mainGoal}
              onChange={(event) => setMainGoal(event.target.value)}
              rows={4}
              className="mt-2 w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Planning pain</span>
            <textarea
              value={planningPain}
              onChange={(event) => setPlanningPain(event.target.value)}
              rows={4}
              className="mt-2 w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Peak focus time</span>
            <textarea
              value={peakFocusTime}
              onChange={(event) => setPeakFocusTime(event.target.value)}
              rows={3}
              className="mt-2 w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Low energy time</span>
            <textarea
              value={lowEnergyTime}
              onChange={(event) => setLowEnergyTime(event.target.value)}
              rows={3}
              className="mt-2 w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Work block length</span>
            <textarea
              value={preferredWorkBlockLength}
              onChange={(event) => setPreferredWorkBlockLength(event.target.value)}
              rows={3}
              className="mt-2 w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block">
            <span className="text-sm font-extrabold text-[var(--ink)]">Sleep preference</span>
            <textarea
              value={sleepPreference}
              onChange={(event) => setSleepPreference(event.target.value)}
              rows={3}
              className="mt-2 w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>

          <label className="block sm:col-span-2">
            <span className="text-sm font-extrabold text-[var(--ink)]">Default planning brief</span>
            <textarea
              value={firstPrompt}
              onChange={(event) => setFirstPrompt(event.target.value)}
              rows={5}
              className="mt-2 w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition focus:border-[rgba(20,184,166,0.42)]"
            />
          </label>
        </div>

        <div className="mt-6 flex flex-col gap-3 border-t border-[rgba(124,58,237,0.12)] pt-5 sm:flex-row sm:justify-end">
          <button type="button" onClick={onClose} className="secondary-button min-h-11 px-5">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSave || saving}
            className="primary-button min-h-11 px-5 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {saving ? "Saving..." : "Save preferences"}
          </button>
        </div>
      </div>
    </div>
  );
}
