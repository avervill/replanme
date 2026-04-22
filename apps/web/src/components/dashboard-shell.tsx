"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Navbar } from "@/components/navbar";
import { AiChatPanel } from "@/components/ai-chat-panel";
import {
  ScheduleWorkspace,
  type CalendarView,
} from "@/components/schedule-workspace";

export function DashboardShell() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [view, setView] = useState<CalendarView>("week");
  const [calendarRefreshKey, setCalendarRefreshKey] = useState(0);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, router, user]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-ink border-t-transparent" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-[1680px] px-4 py-6 md:px-6 xl:px-8">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_400px]">
          <ScheduleWorkspace
            view={view}
            onViewChange={setView}
            hasGoogleCalendar={user.has_google_calendar}
            timezone={user.timezone}
            refreshKey={calendarRefreshKey}
          />
          <AiChatPanel
            timeframe={view}
            onCalendarChanged={() => setCalendarRefreshKey((current) => current + 1)}
          />
        </div>
      </main>
    </>
  );
}
