import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard-shell";

export const metadata: Metadata = {
  title: "Dashboard | Resched.me",
  description: "Private Resched.me workspace for calendar planning and AI scheduling.",
  robots: {
    index: false,
    follow: false,
  },
};

export default function DashboardPage() {
  return <DashboardShell />;
}
