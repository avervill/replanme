"use client";

import { useState } from "react";
import {
  saveOnboarding,
  type OnboardingData,
  type OnboardingStatus,
  type UserProfile,
} from "@/lib/api";
import {
  MultiOptionGrid,
  OptionGrid,
  blockLengthOptions,
  goalOptions,
  lowEnergyOptions,
  painOptions,
  peakFocusOptions,
  roleOptions,
  sleepOptions,
  type MultiValue,
} from "@/components/onboarding/preference-options";

type AccountSettingsModalProps = {
  user: UserProfile;
  onboardingStatus: OnboardingStatus | null;
  onClose: () => void;
  onPreferencesSaved?: (status: OnboardingStatus) => void;
};

type SettingsEnergyProfile = {
  peakFocusTime: MultiValue;
  lowEnergyTime: MultiValue;
  preferredWorkBlockLength: MultiValue;
  sleepPreference: MultiValue;
};

const emptyEnergy: SettingsEnergyProfile = {
  peakFocusTime: [],
  lowEnergyTime: [],
  preferredWorkBlockLength: [],
  sleepPreference: [],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function textFromValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.filter(Boolean).map(String).join(", ");
  }
  return typeof value === "string" ? value : "";
}

function listFromValue(value: unknown): MultiValue {
  if (Array.isArray(value)) {
    return value.filter(Boolean).map(String);
  }
  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }
  return [];
}

function initialPreferences(status: OnboardingStatus | null, user: UserProfile) {
  const data = isRecord(status?.onboardingData) ? status.onboardingData : {};
  const energy = isRecord(data.energyProfile) ? data.energyProfile : emptyEnergy;

  return {
    role: textFromValue(data.role) || "Just planning life",
    mainGoal: listFromValue(data.mainGoal),
    planningPain: listFromValue(data.planningPain),
    energyProfile: {
      peakFocusTime: listFromValue(energy.peakFocusTime),
      lowEnergyTime: listFromValue(energy.lowEnergyTime),
      preferredWorkBlockLength: listFromValue(energy.preferredWorkBlockLength),
      sleepPreference: listFromValue(energy.sleepPreference),
    },
    calendarIntent: textFromValue(data.calendarIntent) || (user.has_google_calendar ? "Use my calendar to avoid conflicts" : "Let me generate drafts first"),
    firstPrompt: textFromValue(data.firstPrompt) || "Plan my week around my goals, calendar, energy, and realistic focus blocks.",
  };
}

function PreferenceSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-extrabold text-[var(--ink)]">{title}</h3>
      {children}
    </section>
  );
}

export function AccountSettingsModal({ user, onboardingStatus, onClose, onPreferencesSaved }: AccountSettingsModalProps) {
  const initial = initialPreferences(onboardingStatus, user);
  const [role, setRole] = useState(initial.role);
  const [mainGoal, setMainGoal] = useState<MultiValue>(initial.mainGoal);
  const [planningPain, setPlanningPain] = useState<MultiValue>(initial.planningPain);
  const [energyProfile, setEnergyProfile] = useState<SettingsEnergyProfile>(initial.energyProfile);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = Boolean(
    role.trim() &&
      mainGoal.length > 0 &&
      planningPain.length > 0 &&
      Object.values(energyProfile).every((value) => value.length > 0),
  );

  const submit = async () => {
    if (!canSave || saving) return;
    setSaving(true);
    setSaved(false);
    setError(null);

    const data: OnboardingData = {
      role: role.trim(),
      mainGoal,
      planningPain,
      energyProfile,
      calendarIntent: initial.calendarIntent,
      firstPrompt: initial.firstPrompt,
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

        <div className="mt-6 space-y-6">
          <PreferenceSection title="Role">
            <OptionGrid options={roleOptions} value={role} onChange={setRole} />
          </PreferenceSection>

          <PreferenceSection title="Main goals">
            <MultiOptionGrid options={goalOptions} value={mainGoal} onChange={setMainGoal} />
          </PreferenceSection>

          <PreferenceSection title="Planning pain">
            <MultiOptionGrid options={painOptions} value={planningPain} onChange={setPlanningPain} />
          </PreferenceSection>

          <div className="grid gap-5 lg:grid-cols-2">
            <PreferenceSection title="Peak focus time">
              <MultiOptionGrid
                options={peakFocusOptions}
                value={energyProfile.peakFocusTime}
                onChange={(value) => setEnergyProfile((current) => ({ ...current, peakFocusTime: value }))}
              />
            </PreferenceSection>

            <PreferenceSection title="Low energy time">
              <MultiOptionGrid
                options={lowEnergyOptions}
                value={energyProfile.lowEnergyTime}
                onChange={(value) => setEnergyProfile((current) => ({ ...current, lowEnergyTime: value }))}
              />
            </PreferenceSection>

            <PreferenceSection title="Work block length">
              <MultiOptionGrid
                options={blockLengthOptions}
                value={energyProfile.preferredWorkBlockLength}
                onChange={(value) => setEnergyProfile((current) => ({ ...current, preferredWorkBlockLength: value }))}
              />
            </PreferenceSection>

            <PreferenceSection title="Sleep preference">
              <MultiOptionGrid
                options={sleepOptions}
                value={energyProfile.sleepPreference}
                onChange={(value) => setEnergyProfile((current) => ({ ...current, sleepPreference: value }))}
              />
            </PreferenceSection>
          </div>
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
