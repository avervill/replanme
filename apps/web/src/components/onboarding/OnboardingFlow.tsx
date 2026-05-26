"use client";

import { useMemo, useState } from "react";
import { type OnboardingData, type UserProfile } from "@/lib/api";
import { storePendingInitialPrompt, useOnboarding } from "@/hooks/useOnboarding";
import { useAiPromptTools } from "@/hooks/useAiPromptTools";
import { AiPromptTools } from "@/components/ai-prompt-tools";
import { OnboardingStep } from "@/components/onboarding/OnboardingStep";
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

type OnboardingFlowProps = {
  user: UserProfile;
  onFinished: (firstPrompt?: string) => void;
  onClose?: () => void;
  mode?: "first-run" | "settings";
};

type EnergyProfile = OnboardingData["energyProfile"];

const defaultEnergy: EnergyProfile = {
  peakFocusTime: [],
  lowEnergyTime: [],
  preferredWorkBlockLength: [],
  sleepPreference: [],
};

function formatSelection(value: string | string[] | undefined, fallback: string) {
  if (Array.isArray(value)) return value.length > 0 ? value.join(", ") : fallback;
  return value || fallback;
}

function includesSelection(value: string | string[], option: string) {
  return Array.isArray(value) ? value.includes(option) : value === option;
}

function generatePrompt(role: string, mainGoal: MultiValue, planningPain: MultiValue, energy: EnergyProfile, calendarIntent: string) {
  const focus = formatSelection(energy.peakFocusTime, "my peak focus time");
  const low = formatSelection(energy.lowEnergyTime, "my low-energy hours");
  const block = formatSelection(energy.preferredWorkBlockLength, "realistic");
  const sleep = formatSelection(energy.sleepPreference, "my sleep needs");
  const pain = formatSelection(planningPain, "my planning pain");
  const calendar = calendarIntent === "Let me generate drafts first"
    ? "Create a draft first so I can review it before applying anything."
    : "Use my calendar to avoid conflicts and free time collisions.";

  if (role === "Student" || includesSelection(mainGoal, "Study / exam planning")) {
    return `Plan my week for studying. Put the hardest study blocks during ${focus}, use ${block} work blocks, keep breaks between sessions, respect ${sleep}, and avoid overloading ${low}. ${calendar}`;
  }
  if (role === "Manager" || includesSelection(mainGoal, "Work tasks and meetings")) {
    return `Optimize my week around meetings, deep work, admin tasks, and recovery time. Protect focus blocks during ${focus}, reduce context switching, use ${block} work blocks, and avoid overloading ${low}. ${calendar}`;
  }
  if (role === "Founder") {
    return `Plan my week around product work, marketing, deep work, and admin tasks. Prioritize high-impact work during ${focus}, keep ${block} focus blocks realistic, respect ${sleep}, and avoid overpacking the week. ${calendar}`;
  }
  if (includesSelection(mainGoal, "Fitness and habits")) {
    return `Create a weekly routine with workouts, recovery, meals, and focused work blocks. Keep it realistic, use ${block} blocks for demanding work, respect ${sleep}, and avoid overpacking ${low}. ${calendar}`;
  }
  if (includesSelection(mainGoal, "Overloaded calendar optimization")) {
    return `Optimize my overloaded calendar this week. Protect deep work during ${focus}, move flexible work away from ${low}, preserve recovery time, and make the plan realistic. ${calendar}`;
  }
  return `Plan my week around my main goals, routines, and calendar. Use ${block} work blocks, put important work during ${focus}, avoid ${low}, account for "${pain}", and respect ${sleep}. ${calendar}`;
}

export function OnboardingFlow({ user, onFinished, onClose, mode = "first-run" }: OnboardingFlowProps) {
  const onboarding = useOnboarding(false);
  const [step, setStep] = useState(1);
  const [role, setRole] = useState("");
  const [mainGoal, setMainGoal] = useState<MultiValue>([]);
  const [planningPain, setPlanningPain] = useState<MultiValue>([]);
  const [energyProfile, setEnergyProfile] = useState<EnergyProfile>(defaultEnergy);
  const [firstPrompt, setFirstPrompt] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const calendarIntent = user.has_google_calendar ? "Use my calendar to avoid conflicts" : "Let me generate drafts first";
  const promptTools = useAiPromptTools({
    onTranscript: (text) => setFirstPrompt((current) => (current.trim() ? `${current.trim()} ${text}` : text)),
  });

  const generatedPrompt = useMemo(
    () => generatePrompt(role, mainGoal, planningPain, energyProfile, calendarIntent),
    [role, mainGoal, planningPain, energyProfile, calendarIntent],
  );

  const data: OnboardingData = {
    role,
    mainGoal,
    planningPain,
    energyProfile,
    calendarIntent,
    firstPrompt: firstPrompt.trim() || generatedPrompt,
  };

  const canContinue = (() => {
    if (step === 1) return true;
    if (step === 2) return Boolean(role);
    if (step === 3) return mainGoal.length > 0;
    if (step === 4) return planningPain.length > 0;
    if (step === 5) return Object.values(energyProfile).every((value) => Array.isArray(value) && value.length > 0);
    if (step === 6) return Boolean((firstPrompt.trim() || generatedPrompt).trim());
    return false;
  })();

  const finish = async (generate: boolean) => {
    setSaving(true);
    setError(null);
    try {
      if (promptTools.uploading || promptTools.transcribing || promptTools.recording) return;
      await onboarding.save(data);
      await onboarding.complete();
      if (generate) {
        storePendingInitialPrompt(data.firstPrompt, promptTools.attachments);
      }
      onFinished(generate ? data.firstPrompt : undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save onboarding. Your answers are still here.");
    } finally {
      setSaving(false);
    }
  };

  const skip = async () => {
    setSaving(true);
    setError(null);
    try {
      await onboarding.skip();
      onFinished();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not skip onboarding. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const footer = (
    <div className="mt-8 flex flex-col gap-3 border-t border-[rgba(124,58,237,0.12)] pt-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex gap-3">
        {step > 1 && (
          <button type="button" onClick={() => setStep((current) => Math.max(1, current - 1))} className="secondary-button min-h-11 px-5">
            Back
          </button>
        )}
        {mode === "settings" && onClose && (
          <button type="button" onClick={onClose} className="secondary-button min-h-11 px-5">
            Close
          </button>
        )}
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        {step === 1 && mode === "first-run" && (
          <button type="button" onClick={() => void skip()} disabled={saving} className="secondary-button min-h-11 px-5">
            Skip for now
          </button>
        )}
        {step < 6 ? (
          <button
            type="button"
            onClick={() => setStep((current) => Math.min(6, current + 1))}
            disabled={!canContinue || saving}
            className="primary-button min-h-11 px-5 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {step === 1 ? "Start setup" : "Continue"}
          </button>
        ) : (
          <>
            <button type="button" onClick={() => void finish(false)} disabled={saving || promptTools.uploading || promptTools.transcribing || promptTools.recording} className="secondary-button min-h-11 px-5">
              Finish without generating
            </button>
            <button
              type="button"
              onClick={() => void finish(true)}
              disabled={!canContinue || saving || promptTools.uploading || promptTools.transcribing || promptTools.recording}
              className="primary-button min-h-11 px-5 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {saving ? "Preparing your dashboard..." : "Generate my first plan"}
            </button>
          </>
        )}
      </div>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[140] overflow-y-auto bg-[rgba(76,29,149,0.22)] px-4 py-5 backdrop-blur-xl sm:py-8">
      <div className="mx-auto flex min-h-[calc(100vh-40px)] max-w-5xl items-center justify-center">
        <div className="dashboard-modal w-full rounded-[1.5rem] p-5 shadow-xl sm:p-7">
          {error && (
            <div className="mb-5 rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm font-bold text-red-700">
              {error}
            </div>
          )}

          {step === 1 && (
            <OnboardingStep
              step={1}
              totalSteps={6}
              title="Plan your week with AI, not with mental suffering"
              subtitle="replanme helps you turn messy goals, exams, work, routines, and calendar chaos into a real schedule."
            >
              <div className="grid gap-4 md:grid-cols-3">
                {["Goals become blocks", "Calendar conflicts stay visible", "Your energy shapes the plan"].map((item) => (
                  <div key={item} className="rounded-2xl border border-[rgba(124,58,237,0.12)] bg-white/58 p-4">
                    <p className="text-sm font-extrabold text-[var(--ink)]">{item}</p>
                    <p className="mt-2 text-sm font-semibold leading-6 text-[rgba(60,44,96,0.62)]">
                      We collect planning context now so the first AI draft is useful, not decorative.
                    </p>
                  </div>
                ))}
              </div>
            </OnboardingStep>
          )}

          {step === 2 && (
            <OnboardingStep step={2} totalSteps={6} title="What describes you best?">
              <OptionGrid options={roleOptions} value={role} onChange={setRole} />
            </OnboardingStep>
          )}

          {step === 3 && (
            <OnboardingStep step={3} totalSteps={6} title="What do you want replanme to help with first?">
              <MultiOptionGrid options={goalOptions} value={mainGoal} onChange={setMainGoal} />
            </OnboardingStep>
          )}

          {step === 4 && (
            <OnboardingStep step={4} totalSteps={6} title="What usually breaks your planning?">
              <MultiOptionGrid options={painOptions} value={planningPain} onChange={setPlanningPain} />
            </OnboardingStep>
          )}

          {step === 5 && (
            <OnboardingStep step={5} totalSteps={6} title="Energy profile" subtitle="These answers help the planner put harder work where it belongs.">
              <div className="grid gap-5 lg:grid-cols-2">
                <div>
                  <p className="mb-2 text-sm font-extrabold">When do you usually focus best?</p>
                  <MultiOptionGrid options={peakFocusOptions} value={energyProfile.peakFocusTime as MultiValue} onChange={(value) => setEnergyProfile((current) => ({ ...current, peakFocusTime: value }))} />
                </div>
                <div>
                  <p className="mb-2 text-sm font-extrabold">When do you usually crash?</p>
                  <MultiOptionGrid options={lowEnergyOptions} value={energyProfile.lowEnergyTime as MultiValue} onChange={(value) => setEnergyProfile((current) => ({ ...current, lowEnergyTime: value }))} />
                </div>
                <div>
                  <p className="mb-2 text-sm font-extrabold">How long should deep work blocks usually be?</p>
                  <MultiOptionGrid options={blockLengthOptions} value={energyProfile.preferredWorkBlockLength as MultiValue} onChange={(value) => setEnergyProfile((current) => ({ ...current, preferredWorkBlockLength: value }))} />
                </div>
                <div>
                  <p className="mb-2 text-sm font-extrabold">What should the planner respect?</p>
                  <MultiOptionGrid options={sleepOptions} value={energyProfile.sleepPreference as MultiValue} onChange={(value) => setEnergyProfile((current) => ({ ...current, sleepPreference: value }))} />
                </div>
              </div>
            </OnboardingStep>
          )}

          {step === 6 && (
            <OnboardingStep
              step={6}
              totalSteps={6}
              title="Generate your first useful plan"
              subtitle={`You have ${user.planning_credits} planning credits available. This will create a draft first, then you choose whether to apply it.`}
            >
              <label htmlFor="firstPrompt" className="text-sm font-extrabold text-[var(--ink)]">Editable first prompt</label>
              <textarea
                id="firstPrompt"
                value={firstPrompt}
                onChange={(event) => setFirstPrompt(event.target.value)}
                onPaste={promptTools.handlePaste}
                placeholder={`Example: ${generatedPrompt}`}
                rows={7}
                className="mt-3 w-full resize-none rounded-2xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition placeholder:text-[rgba(35,25,66,0.34)] focus:border-[rgba(20,184,166,0.42)]"
              />
              <div className="mt-3">
                <AiPromptTools
                  attachments={promptTools.attachments}
                  disabled={saving}
                  error={promptTools.error}
                  fileInputRef={promptTools.fileInputRef}
                  onFilesSelected={(files) => void promptTools.uploadFiles(files)}
                  onOpenFilePicker={promptTools.openFilePicker}
                  onRemoveAttachment={promptTools.removeAttachment}
                  onToggleRecording={() => void promptTools.toggleRecording()}
                  recording={promptTools.recording}
                  transcribing={promptTools.transcribing}
                  uploading={promptTools.uploading}
                  uploadProgress={promptTools.uploadProgress}
                />
              </div>
            </OnboardingStep>
          )}

          {footer}
        </div>
      </div>
    </div>
  );
}
