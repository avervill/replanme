"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Navbar } from "@/components/navbar";
import { AiChatPanel } from "@/components/ai-chat-panel";
import { AccountSettingsModal } from "@/components/account-settings-modal";
import { PaywallModal } from "@/components/paywall-modal";
import { OnboardingFlow } from "@/components/onboarding/OnboardingFlow";
import { useOnboarding } from "@/hooks/useOnboarding";
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
  const onboarding = useOnboarding(Boolean(user));

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, router, user]);

  if (loading || !user || onboarding.loading || (!onboarding.status && !onboarding.error)) {
    return (
      <div className="landing-page flex min-h-screen items-center justify-center">
        <div className="w-[min(92vw,520px)] rounded-[1.5rem] border border-white/70 bg-white/60 p-6 shadow-[0_22px_70px_rgba(74,34,129,0.14)] backdrop-blur-xl">
          <div className="h-3 w-28 animate-pulse rounded-full bg-[rgba(124,58,237,0.18)]" />
          <div className="mt-5 h-8 w-3/4 animate-pulse rounded-full bg-[rgba(124,58,237,0.14)]" />
          <div className="mt-3 h-4 w-full animate-pulse rounded-full bg-[rgba(20,184,166,0.13)]" />
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            <div className="h-20 animate-pulse rounded-2xl bg-white/70" />
            <div className="h-20 animate-pulse rounded-2xl bg-white/70" />
          </div>
        </div>
      </div>
    );
  }

  if (onboarding.error && !onboarding.status) {
    return (
      <div className="landing-page flex min-h-screen items-center justify-center px-4">
        <div className="dashboard-modal w-full max-w-md rounded-[1.5rem] p-6 text-center">
          <p className="mini-label mx-auto">Setup check</p>
          <h1 className="mt-4 max-w-none text-2xl">Could not load onboarding status</h1>
          <p className="mt-3 text-sm font-semibold leading-6 text-[rgba(60,44,96,0.68)]">{onboarding.error}</p>
          <button type="button" onClick={() => void onboarding.refresh()} className="primary-button mt-6 min-h-11 px-5">
            Retry
          </button>
        </div>
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
      {settingsOpen && (
        <AccountSettingsModal
          user={user}
          onboardingStatus={onboarding.status}
          onClose={() => setSettingsOpen(false)}
          onPreferencesSaved={() => void onboarding.refresh()}
        />
      )}
      <PaywallModal paywall={paywall} onClose={() => setPaywall(null)} />
      {onboarding.shouldShowOnboarding && (
        <OnboardingFlow
          user={user}
          mode="first-run"
          onFinished={() => {
            void onboarding.refresh();
          }}
        />
      )}
    </div>
  );
}
