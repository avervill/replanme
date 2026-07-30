export type SessionUser = {
  id: string;
  email: string;
  full_name: string | null;
  timezone: string;
  has_google_calendar: boolean;
};

export type SessionResponse = {
  authenticated: boolean;
  user: SessionUser | null;
};

export type CalendarChange = {
  type: "create" | "update" | "delete";
  client_ref?: string;
  event_id?: string;
  title?: string;
  start_at?: string;
  end_at?: string;
  timezone?: string;
  reason?: string;
};

export type CalendarChangePlan = {
  id: string;
  summary: string;
  changes: CalendarChange[];
  conflicts: Array<{ change_ref: string; event_id?: string; summary: string; severity: "info" | "warning" | "blocking" }>;
  warnings: string[];
  status: "pending" | "applying" | "applied" | "expired" | "failed" | "cancelled";
  expires_at: string;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(payload.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getSession() {
  return apiFetch<SessionResponse>("/auth/session", { cache: "no-store" });
}

export async function logoutSession() {
  await apiFetch<{ detail: string }>("/auth/logout", { method: "POST" });
}

export async function beginGoogleLogin() {
  window.location.assign("/api/v1/auth/google/start");
}

export async function streamAssistantMessage(
  message: string,
  timezone: string,
  onEvent: (event: string, payload: Record<string, unknown>) => void,
) {
  const response = await fetch("/api/v1/assistant/messages", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, timezone }),
  });
  if (!response.ok || !response.body) throw new Error("The planning stream could not start");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = block.match(/^event:\s*(.+)$/m)?.[1];
      const data = block.match(/^data:\s*(.+)$/m)?.[1];
      if (event && data) onEvent(event, JSON.parse(data));
    }
    if (done) break;
  }
}

export function applyCalendarPlan(planId: string) {
  return apiFetch<{ plan: CalendarChangePlan; applied_event_ids: string[]; rolled_back: boolean }>(
    `/plans/${planId}/apply`,
    { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() } },
  );
}

export function updateCalendarPlan(plan: CalendarChangePlan) {
  return apiFetch<CalendarChangePlan>(`/plans/${plan.id}`, {
    method: "PUT",
    body: JSON.stringify({
      summary: plan.summary,
      changes: plan.changes,
      conflicts: plan.conflicts,
      warnings: plan.warnings,
    }),
  });
}

export function importScheduleImage(file: File, timezone = "UTC") {
  const form = new FormData();
  form.append("file", file);
  form.append("timezone", timezone);
  return apiFetch<CalendarChangePlan>("/imports/image", { method: "POST", body: form });
}

export function transcribeVoice(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<{ transcript: string; detected_language: string }>("/voice/transcribe", { method: "POST", body: form });
}
