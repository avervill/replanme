import type { Metadata } from "next";
import { CalendarExperience } from "@/components/calendar-experience";

export const metadata: Metadata = {
  title: "Interactive demo",
  description: "Explore a realistic read-only student week in replanme.",
};

export default function DemoPage() {
  return <CalendarExperience mode="demo" />;
}
