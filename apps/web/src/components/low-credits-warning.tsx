"use client";

type LowCreditsWarningProps = {
  credits: number;
};

export function LowCreditsWarning({ credits }: LowCreditsWarningProps) {
  if (credits > 3) return null;
  return <span className="low-credits-warning">{credits} credits left</span>;
}
