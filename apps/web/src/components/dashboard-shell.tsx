"use client";

import Link from "next/link";
import { CalendarX2, CloudOff, LoaderCircle, LogIn } from "lucide-react";
import { CalendarExperience } from "@/components/calendar-experience";
import { useAuth } from "@/lib/auth";

export function DashboardShell() {
  const { user, loading, error, refresh } = useAuth();

  if (loading) {
    return <DashboardState icon={<LoaderCircle className="animate-spin" />} title="Loading your week…" body="Checking your secure session and calendar connection." />;
  }
  if (error === "offline") {
    return <DashboardState icon={<CloudOff />} title="You’re offline" body="Your calendar is safe. Reconnect to load the latest events and planning proposals." action={<button className="button primary" onClick={() => void refresh()}>Try again</button>} />;
  }
  if (!user) {
    return <DashboardState icon={<LogIn />} title="Your session has expired" body="Sign in again to continue. No calendar changes were made." action={<Link className="button primary" href="/login">Sign in with Google</Link>} />;
  }
  if (!user.has_google_calendar) {
    return <DashboardState icon={<CalendarX2 />} title="Google Calendar is disconnected" body="Reconnect your calendar before asking AI to plan or apply changes." action={<Link className="button primary" href="/login">Reconnect calendar</Link>} />;
  }
  return <CalendarExperience mode="dashboard" />;
}

function DashboardState({ icon, title, body, action }: { icon: React.ReactNode; title: string; body: string; action?: React.ReactNode }) {
  return (
    <main className="state-card">
      <div className="state-content">
        <div className="feature-icon" style={{ margin: "auto" }}>{icon}</div>
        <h1>{title}</h1>
        <p>{body}</p>
        {action && <div style={{ marginTop: 20 }}>{action}</div>}
      </div>
    </main>
  );
}
