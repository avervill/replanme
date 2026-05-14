"use client";

import type { ReactNode } from "react";

type OnboardingStepProps = {
  step: number;
  totalSteps: number;
  title: string;
  subtitle?: string;
  children: ReactNode;
};

export function OnboardingStep({ step, totalSteps, title, subtitle, children }: OnboardingStepProps) {
  const progress = Math.round((step / totalSteps) * 100);

  return (
    <section className="space-y-6" aria-labelledby={`onboarding-step-${step}`}>
      <div>
        <div className="flex items-center justify-between gap-4">
          <p className="mini-label">Step {step} of {totalSteps}</p>
          <p className="text-xs font-extrabold text-[rgba(60,44,96,0.58)]">{progress}%</p>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/60">
          <div
            className="h-full rounded-full bg-[linear-gradient(135deg,var(--purple),var(--teal))] transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div>
        <h1 id={`onboarding-step-${step}`} className="max-w-none text-3xl font-black leading-tight sm:text-4xl">
          {title}
        </h1>
        {subtitle && <p className="mt-3 max-w-2xl text-sm font-semibold leading-6 text-[rgba(60,44,96,0.68)]">{subtitle}</p>}
      </div>

      {children}
    </section>
  );
}

