/**
 * Typed API client with auth headers and error handling.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
export const AUTH_TOKEN_STORAGE_KEY = "resched_me_token";
const LEGACY_AUTH_TOKEN_STORAGE_KEY = "reschedai_token";

export function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  if (token) return token;

  const legacyToken = localStorage.getItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
  if (legacyToken) {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, legacyToken);
    localStorage.removeItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
  }

  return legacyToken;
}

export function writeAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  localStorage.removeItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
}

export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  localStorage.removeItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
}

function authHeaders(): HeadersInit {
  const token = readAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

/** GET request with auth */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
  });
  return handleResponse<T>(res);
}

/** POST request with auth */
export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

/** PUT request with auth */
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    cache: "no-store",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<T>(res);
}

/** DELETE request with auth */
export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    cache: "no-store",
    headers: { ...authHeaders() },
  });
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
}

/** Get the Google OAuth URL from the backend */
export async function getGoogleAuthUrl(): Promise<string> {
  const data = await apiGet<{ authorization_url: string }>("/auth/google/url");
  return data.authorization_url;
}

/** User profile type */
export interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  timezone: string;
  has_google_calendar: boolean;
}

/** Fetch the current user profile */
export async function fetchMe(): Promise<UserProfile> {
  return apiGet<UserProfile>("/auth/me");
}

export interface GoogleCalendarEvent {
  id: string;
  title: string;
  description: string | null;
  start: {
    dateTime?: string;
    date?: string;
    timeZone?: string;
  };
  end: {
    dateTime?: string;
    date?: string;
    timeZone?: string;
  };
  location: string | null;
  status: string;
  html_link: string | null;
}

export interface PlannerAction {
  kind: "create_event" | "update_event" | "protect_focus_block" | "ask_user";
  summary: string;
}

export interface PlannerResponse {
  plan_summary: string;
  actions: PlannerAction[];
  approval_required: boolean;
}

export interface CreateEventFromPromptResponse {
  created: boolean;
  message: string;
  event: GoogleCalendarEvent | null;
  events: GoogleCalendarEvent[];
  extracted: {
    title: string;
    description: string | null;
    start_at: string;
    end_at: string;
    timezone: string;
    location: string | null;
  } | null;
  extracted_events: Array<{
    title: string;
    description: string | null;
    start_at: string;
    end_at: string;
    timezone: string;
    location: string | null;
  }>;
}

export interface CalendarEventInput {
  title: string;
  description?: string | null;
  start_at: string;
  end_at: string;
  timezone: string;
  location?: string | null;
  reminders?: number[];
}

export interface CalendarEventUpdateInput {
  title?: string;
  description?: string | null;
  start_at?: string;
  end_at?: string;
  timezone?: string;
  location?: string | null;
}

export async function fetchCalendarEvents(): Promise<GoogleCalendarEvent[]> {
  return apiGet<GoogleCalendarEvent[]>("/calendar/events");
}

export async function createCalendarEvent(
  payload: CalendarEventInput,
): Promise<GoogleCalendarEvent> {
  return apiPost<GoogleCalendarEvent>("/calendar/events", payload);
}

export async function updateCalendarEvent(
  eventId: string,
  payload: CalendarEventUpdateInput,
): Promise<GoogleCalendarEvent> {
  return apiPut<GoogleCalendarEvent>(`/calendar/events/${eventId}`, payload);
}

export async function deleteCalendarEvent(eventId: string): Promise<void> {
  return apiDelete(`/calendar/events/${eventId}`);
}

export async function planSchedule(input: {
  prompt: string;
  timeframe: "week" | "month";
  constraints?: string[];
}): Promise<PlannerResponse> {
  return apiPost<PlannerResponse>("/ai/plan", input);
}

export async function createEventFromPrompt(input: {
  prompt: string;
  timezone: string;
}): Promise<CreateEventFromPromptResponse> {
  return apiPost<CreateEventFromPromptResponse>("/ai/create-event", input);
}
