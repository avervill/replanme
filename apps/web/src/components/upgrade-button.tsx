"use client";

import Link from "next/link";
import { trackUpgradeClicked } from "@/lib/api";

type UpgradeButtonProps = {
  className?: string;
  children?: string;
};

export function UpgradeButton({ className, children = "Upgrade to Pro" }: UpgradeButtonProps) {
  return (
    <Link
      href="/pricing"
      onClick={() => {
        void trackUpgradeClicked("upgrade_button").catch(() => undefined);
      }}
      className={className ?? "upgrade-button"}
    >
      {children}
    </Link>
  );
}
