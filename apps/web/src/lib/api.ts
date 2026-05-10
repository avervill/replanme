/**
 * Typed API client with auth headers and error handling.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
export const AUTH_TOKEN_STORAGE_KEY = "replanme_token";
const LEGACY_AUTH_TOKEN_STORAGE_KEYS = ["resched_me_token", "reschedai_token"];

export function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  if (token) return token;

  for (const legacyKey of LEGACY_AUTH_TOKEN_STORAGE_KEYS) {
    const legacyToken = localStorage.getItem(legacyKey);
    if (legacyToken) {
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, legacyToken);
      localStorage.removeItem(legacyKey);
      return legacyToken;
    }
  }

  return null;
}

export function writeAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  LEGACY_AUTH_TOKEN_STORAGE_KEYS.forEach((legacyKey) => localStorage.removeItem(legacyKey));
}

export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  LEGACY_AUTH_TOKEN_STORAGE_KEYS.forEach((legacyKey) => localStorage.removeItem(legacyKey));
}

function authHeaders(): HeadersInit {
  const token = readAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface PaywallPayload {
  ok: false;
  type?: "paywall";
  error: "PAYWALL_REQUIRED" | "PRO_FEATURE_REQUIRED";
  reason?: "NO_CREDITS" | "NOT_ENOUGH_CREDITS" | "FEATURE_LOCKED" | "MONTHLY_LIMIT_REACHED" | "SUBSCRIPTION_INACTIVE";
  feature: string | null;
  message: string;
  upgradeMessage: string;
  currentPlan: "free" | "pro" | "admin";
  requiredCredits?: number;
  availableCredits?: number;
  paywall?: {
    title: string;
    description: string;
    primaryAction: string;
    secondaryAction: string;
  };
  limit?: number;
  used?: number;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export class PaywallApiError extends ApiError {
  constructor(status: number, public payload: PaywallPayload) {
    super(status, payload.message);
    this.name = "PaywallApiError";
  }
}

export function isPaywallPayload(value: unknown): value is PaywallPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as Partial<PaywallPayload>;
  return (
    payload.ok === false &&
    (payload.error === "PAYWALL_REQUIRED" || payload.error === "PRO_FEATURE_REQUIRED") &&
    typeof payload.message === "string" &&
    typeof payload.upgradeMessage === "string"
  );
}

export function isPaywallError(error: unknown): error is PaywallApiError {
  return error instanceof PaywallApiError;
}

function errorMessageFromBody(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const data = body as { detail?: unknown; message?: unknown; error?: unknown };
  if (typeof data.detail === "string") return data.detail;
  if (typeof data.message === "string") return data.message;
  if (typeof data.error === "string") return data.error;
  return fallback;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const paywall = isPaywallPayload(body)
      ? body
      : isPaywallPayload((body as { detail?: unknown })?.detail)
        ? (body as { detail: PaywallPayload }).detail
        : null;
    if (paywall) {
      throw new PaywallApiError(res.status, paywall);
    }
    throw new ApiError(res.status, errorMessageFromBody(body, "Request failed"));
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
    const paywall = isPaywallPayload(body)
      ? body
      : isPaywallPayload((body as { detail?: unknown })?.detail)
        ? (body as { detail: PaywallPayload }).detail
        : null;
    if (paywall) {
      throw new PaywallApiError(res.status, paywall);
    }
    throw new ApiError(res.status, errorMessageFromBody(body, "Request failed"));
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
  plan: "free" | "pro" | "admin";
  subscription_status: string;
  planning_credits: number;
  is_admin: boolean;
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

export interface AssistantPreviewChange {
  action:
  | "create_event"
  | "edit_event"
  | "delete_event"
  | "duplicate_events"
  | "fetch_events"
  | "move_event"
  | "find_free_slots"
  | "summarize_schedule"
  | "detect_conflicts"
  | "optimize_schedule";
  title: string;
  details: string;
  current_start_at?: string | null;
  proposed_start_at?: string | null;
  proposed_end_at?: string | null;
}

export interface AssistantCalendarEventSnapshot {
  id: string;
  title: string;
  description: string | null;
  start_at: string;
  end_at: string;
  timezone: string;
  location: string | null;
  status: string;
  html_link: string | null;
}

export interface AssistantResponse {
  session_id: string;
  status: "preview" | "awaiting_confirmation" | "completed" | "failed";
  reply: string;
  routing: {
    intent:
    | "CREATE_EVENT"
    | "DELETE_EVENT"
    | "UPDATE_EVENT"
    | "MOVE_EVENT"
    | "DUPLICATE_EVENTS"
    | "PLAN_PERIOD"
    | "OPTIMIZE_SCHEDULE"
    | "SEARCH_EVENTS"
    | "CONFIRMATION_YES"
    | "CONFIRMATION_NO"
    | "CHAT"
    | "UNKNOWN";
    route: "simple" | "complex" | "hybrid";
    selected_model: string;
    confidence: number;
    complexity_score: number;
    use_calendar_context: boolean;
    use_memory: boolean;
    reason: string;
    candidate_tools: string[];
    low_cost_path: boolean;
  };
  plan: {
    goal: string;
    summary: string;
    selected_model: string;
    route: "simple" | "complex" | "hybrid";
    reasoning: string;
    requires_confirmation: boolean;
    confirmation_reason: string | null;
    response_message: string;
  };
  safety: {
    requires_confirmation: boolean;
    risk_level: "low" | "medium" | "high" | "critical";
    reasons: string[];
    impacted_events: number;
  };
  execution: {
    status: "preview" | "awaiting_confirmation" | "completed" | "failed";
    executed_steps: number;
    preview: AssistantPreviewChange[];
    error: string | null;
    created_events: AssistantCalendarEventSnapshot[];
    updated_events: AssistantCalendarEventSnapshot[];
    deleted_events: AssistantCalendarEventSnapshot[];
  };
  display_actions: Array<{ kind: string; summary: string }>;
  referenced_events: AssistantCalendarEventSnapshot[];
  awaiting_confirmation: boolean;
  confirmation_token: string | null;
  estimated_credit_cost: number;
  model_used: string | null;
  complexity_score: number;
  credits?: {
    used: number;
    remaining: number;
  } | null;
}

export interface UploadedFileResponse {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  kind: "image" | "pdf" | "text" | "audio" | "other";
  url: string;
  text_preview: string | null;
}

export interface UsageMetric {
  used: number;
  limit: number | null;
  allowed: boolean;
}

export interface SubscriptionUsageResponse {
  plan: "free" | "pro" | "admin";
  subscriptionStatus: string;
  planningCredits: number;
  creditsLastRefilledAt: string | null;
  lowCredits: boolean;
  periodStart?: string | null;
  periodEnd?: string | null;
  usage: {
    aiActions: UsageMetric;
    weeklyPlans: UsageMetric;
    imageImports: UsageMetric;
    voiceInputs: UsageMetric;
    monthlyPlans: UsageMetric;
    smartReschedules: UsageMetric;
    energySchedules: UsageMetric;
    recurringPlans: UsageMetric;
  };
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

export async function uploadAssistantFile(
  file: File | Blob,
  filename: string,
  onProgress?: (percent: number) => void,
): Promise<UploadedFileResponse> {
  const form = new FormData();
  form.append("file", file, filename);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/uploads`);
    const token = readAuthToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      const body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve(body as UploadedFileResponse);
      } else {
        const paywall = isPaywallPayload(body)
          ? body
          : isPaywallPayload(body?.detail)
            ? body.detail
            : null;
        reject(paywall ? new PaywallApiError(xhr.status, paywall) : new ApiError(xhr.status, errorMessageFromBody(body, "Upload failed")));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Upload failed"));
    xhr.onabort = () => reject(new ApiError(0, "Upload cancelled"));
    xhr.send(form);
  });
}

export async function transcribeVoice(
  file: Blob,
  filename = "recording.webm",
): Promise<{ transcript: string }> {
  const form = new FormData();
  form.append("file", file, filename);
  const res = await fetch(`${API_BASE}/uploads/voice/transcribe`, {
    method: "POST",
    cache: "no-store",
    headers: { ...authHeaders() },
    body: form,
  });
  return handleResponse<{ transcript: string }>(res);
}

export async function fetchSubscriptionUsage(): Promise<SubscriptionUsageResponse> {
  return apiGet<SubscriptionUsageResponse>("/subscription/usage");
}

export interface AdminUserSummary {
  id: string;
  email: string;
  name: string | null;
  plan: "free" | "pro" | "admin";
  planningCredits: number;
  isAdmin: boolean;
  subscriptionStatus: string;
  hasGoogleCalendar: boolean;
  active: boolean;
  totalPlanningRequests: number;
  totalCreditsUsed: number;
  createdAt: string;
}

export interface AdminUsersResponse {
  items: AdminUserSummary[];
  total: number;
  page: number;
  pageSize: number;
}

export interface AdminOverview {
  totalUsers: number;
  newUsersToday: number;
  newUsersLast7Days: number;
  activeUsersToday: number;
  activeUsersLast7Days: number;
  totalPlanningRequests: number;
  successfulPlanningRequests: number;
  failedPlanningRequests: number;
  totalCreditsUsed: number;
  totalCreditsGranted: number;
  googleCalendarConnectedUsers: number;
  paywallViews: number;
  upgradeClicks: number;
}

export interface AdminTimeseriesDay {
  date: string;
  signups: number;
  planningRequests: number;
  creditsUsed: number;
  successfulPlanningRequests: number;
  failedPlanningRequests: number;
}

export interface AdminTimeseries {
  range: "14d" | "30d";
  days: AdminTimeseriesDay[];
}

export interface AdminCreditTransaction {
  id: string;
  amount: number;
  balanceBefore: number;
  balanceAfter: number;
  type: string;
  normalizedType?: string;
  reason: string;
  feature: string | null;
  relatedPlanningRequestId: string | null;
  createdByAdminId: string | null;
  createdAt: string;
}

export interface AdminPlanningRequest {
  id: string;
  prompt: string | null;
  intent: string | null;
  feature: string | null;
  status: string;
  estimatedCredits: number;
  creditsUsed: number;
  modelUsed: string | null;
  latencyMs: number | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AdminUserDetail extends AdminUserSummary {
  creditTransactions: AdminCreditTransaction[];
  planningRequests: AdminPlanningRequest[];
  analyticsEvents?: Array<{
    id: string;
    eventName: string;
    feature: string | null;
    metadata: Record<string, unknown> | null;
    createdAt: string;
  }>;
  paywallEvents?: Array<{
    id: string;
    eventName: string;
    feature: string | null;
    metadata: Record<string, unknown> | null;
    createdAt: string;
  }>;
}

export interface AdminUsersParams {
  page?: number;
  pageSize?: number;
  search?: string;
  sort?: "createdAt" | "credits" | "email";
  admin?: boolean;
  googleConnected?: boolean;
  active?: boolean;
}

function queryString(params: object): string {
  const query = new URLSearchParams();
  Object.entries(params as Record<string, string | number | boolean | undefined>).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const value = query.toString();
  return value ? `?${value}` : "";
}

export async function fetchAdminOverview(): Promise<AdminOverview> {
  return apiGet<AdminOverview>("/admin/analytics/overview");
}

export async function fetchAdminTimeseries(range: "14d" | "30d" = "30d"): Promise<AdminTimeseries> {
  return apiGet<AdminTimeseries>(`/admin/analytics/timeseries${queryString({ range })}`);
}

export async function fetchAdminUsers(params: AdminUsersParams = {}): Promise<AdminUsersResponse> {
  return apiGet<AdminUsersResponse>(`/admin/users${queryString(params)}`);
}

export async function fetchAdminUser(userId: string): Promise<AdminUserDetail> {
  return apiGet<AdminUserDetail>(`/admin/users/${userId}`);
}

export async function adminGrantCredits(userId: string, amount: number, reason: string): Promise<{ ok: boolean; planningCredits: number }> {
  return apiPost<{ ok: boolean; planningCredits: number }>(`/admin/users/${userId}/credits/grant`, { amount, reason });
}

export async function adminAdjustCredits(userId: string, amount: number, reason: string): Promise<{ ok: boolean; planningCredits: number }> {
  return apiPost<{ ok: boolean; planningCredits: number }>(`/admin/users/${userId}/credits/adjust`, { amount, reason });
}

export async function adminSetPlan(userId: string, plan: "free" | "pro" | "admin"): Promise<{ ok: boolean; plan: string; subscriptionStatus: string }> {
  return apiPost<{ ok: boolean; plan: string; subscriptionStatus: string }>(`/admin/users/${userId}/plan`, { plan });
}

export async function trackUpgradeClicked(source: string): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>("/subscription/upgrade-clicked", { source });
}

export async function trackOnboardingEvent(eventName: "onboarding_started" | "onboarding_completed", metadata?: Record<string, unknown>): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>("/subscription/onboarding-event", { eventName, metadata });
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

export interface ChatHistoryResponse {
  session_id: string;
  messages: Array<{
    id: string;
    role: "user" | "assistant";
    text: string;
  }>;
  planning_active: boolean;
  plan_summary: string | null;
}

export async function fetchChatHistory(sessionId: string): Promise<ChatHistoryResponse> {
  return apiGet<ChatHistoryResponse>(`/ai/assistant/history?session_id=${encodeURIComponent(sessionId)}`);
}

export async function clearChatHistory(sessionId: string): Promise<{ session_id: string; cleared: boolean }> {
  return apiDelete(`/ai/assistant/history?session_id=${encodeURIComponent(sessionId)}`) as Promise<any>;
}

export async function sendAssistantMessage(input: {
  prompt?: string;
  timezone: string;
  session_id?: string;
  preview?: boolean;
  dry_run?: boolean;
  confirm?: boolean;
  confirmation_token?: string | null;
  attachments?: UploadedFileResponse[];
}): Promise<AssistantResponse> {
  return apiPost<AssistantResponse>("/ai/assistant", {
    prompt: input.prompt ?? "",
    timezone: input.timezone,
    session_id: input.session_id ?? null,
    preview: input.preview ?? false,
    dry_run: input.dry_run ?? false,
    confirm: input.confirm ?? false,
    confirmation_token: input.confirmation_token ?? null,
    attachments: input.attachments ?? [],
  });
}
