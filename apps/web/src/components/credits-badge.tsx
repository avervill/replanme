"use client";

type CreditsBadgeProps = {
  plan: "free" | "pro" | "admin";
  credits: number;
};

export function CreditsBadge({ plan, credits }: CreditsBadgeProps) {
  const label = plan.charAt(0).toUpperCase() + plan.slice(1);
  const low = credits <= 3 && plan !== "admin";

  return (
    <div className={`credits-badge ${low ? "low" : ""}`} title={`${credits} planning credits`}>
      <span>{label}</span>
      <span aria-hidden="true">·</span>
      <strong>{credits} credits</strong>
    </div>
  );
}
