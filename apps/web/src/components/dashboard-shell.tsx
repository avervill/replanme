"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Navbar } from "@/components/navbar";
import { AiChatPanel } from "@/components/ai-chat-panel";
import { AccountSettingsModal } from "@/components/account-settings-modal";
import { PaywallModal } from "@/components/paywall-modal";
import {
  ScheduleWorkspace,
  type CalendarView,
} from "@/components/schedule-workspace";
import type { PaywallPayload } from "@/lib/api";

export function DashboardShell() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [view, setView] = useState<CalendarView>("week");
  const [calendarRefreshKey, setCalendarRefreshKey] = useState(0);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [paywall, setPaywall] = useState<PaywallPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, router, user]);

  if (loading || !user) {
    return (
      <div className="landing-page flex min-h-screen items-center justify-center">
        <div className="h-10 w-10 animate-pulse rounded-full bg-[linear-gradient(135deg,var(--purple),var(--teal))]" />
      </div>
    );
  }

  return (
    <div className="dashboard-page landing-page">
      <Navbar onSettingsClick={() => setSettingsOpen(true)} />
      <main className="dashboard-main">
        <div className="dashboard-calendar-layer">
          <ScheduleWorkspace
            view={view}
            onViewChange={setView}
            hasGoogleCalendar={user.has_google_calendar}
            timezone={user.timezone}
            refreshKey={calendarRefreshKey}
            onPaywall={setPaywall}
          />
        </div>

        {chatCollapsed ? (
          <button
            type="button"
            onClick={() => setChatCollapsed(false)}
            className="dashboard-chat-open-button"
            aria-label="Open AI assistant"
          >
            AI
          </button>
        ) : (
          <div className="dashboard-chat-overlay">
            <AiChatPanel
              timeframe={view}
              onCollapse={() => setChatCollapsed(true)}
              onCalendarChanged={() => setCalendarRefreshKey((current) => current + 1)}
              onPaywall={setPaywall}
            />
          </div>
        )}
      </main>
      {settingsOpen && <AccountSettingsModal user={user} onClose={() => setSettingsOpen(false)} />}
      <PaywallModal paywall={paywall} onClose={() => setPaywall(null)} />
    </div>
  );
}
