"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ApiError,
  createCalendarEvent,
  deleteCalendarEvent,
  fetchCalendarEvents,
  getGoogleAuthUrl,
  isPaywallError,
  updateCalendarEvent,
  type CalendarEventInput,
  type CalendarEventUpdateInput,
  type GoogleCalendarEvent,
  type PaywallPayload,
} from "@/lib/api";
import { EventCard } from "./event-card";

export type CalendarView = "week" | "month";

type ScheduleWorkspaceProps = {
  view: CalendarView;
  onViewChange: (view: CalendarView) => void;
  hasGoogleCalendar: boolean;
  timezone?: string;
  refreshKey?: number;
  onPaywall?: (payload: PaywallPayload) => void;
};

type NormalizedCalendarEvent = {
  id: string;
  title: string;
  description: string | null;
  location: string | null;
  status: string;
  htmlLink: string | null;
  startAt: Date;
  endAt: Date;
  isAllDay: boolean;
};

type EventDraft = {
  title: string;
  description: string;
  location: string;
  startAt: string;
  endAt: string;
};

type EventEditorState =
  | { mode: "closed" }
  | {
    mode: "create";
    draft: EventDraft;
    error: string | null;
    submitting: boolean;
    deleting: boolean;
  }
  | {
    mode: "edit";
    event: NormalizedCalendarEvent;
    originalDraft: EventDraft;
    draft: EventDraft;
    error: string | null;
    submitting: boolean;
    deleting: boolean;
  };

type DragState = {
  event: NormalizedCalendarEvent;
  originDayIndex: number;
  originStartMinutes: number;
  currentDayIndex: number;
  currentStartAt: Date;
  currentEndAt: Date;
  startClientX: number;
  startClientY: number;
  moved: boolean;
};

type PositionedWeekEvent = {
  event: NormalizedCalendarEvent;
  top: number;
  height: number;
  leftPercent: number;
  widthPercent: number;
};

const WEEK_START_HOUR = 6;
const WEEK_END_HOUR = 24;
const HEADER_HEIGHT = 106;
const ALL_DAY_HEIGHT = 38;
const HOUR_ROW_HEIGHT = 76;
const TIME_COLUMN_WIDTH = 88;
const DRAG_SNAP_MINUTES = 15;

const weekdayFormatter = new Intl.DateTimeFormat("en-US", { weekday: "short" });
const longWeekdayFormatter = new Intl.DateTimeFormat("en-US", { weekday: "long" });
const monthFormatter = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" });
const weekRangeFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
});
const dayNumberFormatter = new Intl.DateTimeFormat("en-US", { day: "numeric" });
const dayTitleFormatter = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
});
const timeFormatter = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
});
const hourLabelFormatter = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
});

function cloneDate(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function startOfWeek(date: Date): Date {
  const value = cloneDate(date);
  const weekday = value.getDay();
  const offset = weekday === 0 ? -6 : 1 - weekday;
  value.setDate(value.getDate() + offset);
  return value;
}

function addDays(date: Date, amount: number): Date {
  const next = cloneDate(date);
  next.setDate(next.getDate() + amount);
  return next;
}

function isSameDay(left: Date, right: Date): boolean {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

function getDateKey(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function parseGoogleDate(value?: string): Date | null {
  if (!value) {
    return null;
  }
  if (value.includes("T")) {
    return new Date(value);
  }
  return new Date(`${value}T00:00:00`);
}

function normalizeEvent(event: GoogleCalendarEvent): NormalizedCalendarEvent | null {
  const startValue = event.start.dateTime ?? event.start.date;
  const endValue = event.end.dateTime ?? event.end.date;
  const startAt = parseGoogleDate(startValue);
  const endAt = parseGoogleDate(endValue);

  if (!startAt || Number.isNaN(startAt.getTime())) {
    return null;
  }

  return {
    id: event.id,
    title: event.title || "Untitled",
    description: event.description,
    location: event.location,
    status: event.status,
    htmlLink: event.html_link,
    startAt,
    endAt: endAt && !Number.isNaN(endAt.getTime()) ? endAt : startAt,
    isAllDay: !event.start.dateTime,
  };
}

function toInputDateTime(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function parseInputDateTime(value: string): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function roundToNextHour(date: Date): Date {
  const next = new Date(date);
  next.setMinutes(0, 0, 0);
  next.setHours(next.getHours() + 1);
  return next;
}

function defaultDraft(date: Date): EventDraft {
  const start = new Date(date);
  const now = new Date();

  if (isSameDay(start, now) && start < now) {
    const rounded = roundToNextHour(now);
    start.setHours(rounded.getHours(), 0, 0, 0);
  } else if (start.getHours() === 0 && start.getMinutes() === 0) {
    start.setHours(9, 0, 0, 0);
  }

  const end = new Date(start);
  end.setHours(end.getHours() + 1);

  return {
    title: "",
    description: "",
    location: "",
    startAt: toInputDateTime(start),
    endAt: toInputDateTime(end),
  };
}

function draftFromEvent(event: NormalizedCalendarEvent): EventDraft {
  return {
    title: event.title,
    description: event.description ?? "",
    location: event.location ?? "",
    startAt: toInputDateTime(event.startAt),
    endAt: toInputDateTime(event.endAt),
  };
}

function equalDraftValue(left: string, right: string): boolean {
  return left.trim() === right.trim();
}

function formatTimeRange(event: NormalizedCalendarEvent): string {
  if (event.isAllDay) {
    return "All day";
  }
  return `${timeFormatter.format(event.startAt)} - ${timeFormatter.format(event.endAt)}`;
}

function getMinutesSinceMidnight(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

function buildDateForDayAndMinutes(day: Date, totalMinutes: number): Date {
  const next = cloneDate(day);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  next.setHours(hours, minutes, 0, 0);
  return next;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function buildWeekDays(anchorDate: Date): Date[] {
  const weekStart = startOfWeek(anchorDate);
  return Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
}

function buildMonthGrid(anchorDate: Date): Date[] {
  const monthStart = new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1);
  const gridStart = startOfWeek(monthStart);
  return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
}

function formatTimezoneLabel(timezone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date());
    const offset = parts.find((part) => part.type === "timeZoneName")?.value ?? timezone;
    return offset.replace("GMT", "GMT");
  } catch {
    return timezone;
  }
}

function getWeekEventLayout(event: NormalizedCalendarEvent): { top: number; height: number } {
  const startHourValue = event.startAt.getHours() + event.startAt.getMinutes() / 60;
  const endHourValue = event.endAt.getHours() + event.endAt.getMinutes() / 60;
  const clampedStart = Math.max(startHourValue, WEEK_START_HOUR);
  const clampedEnd = Math.min(Math.max(endHourValue, clampedStart + 0.5), WEEK_END_HOUR);

  return {
    top: (clampedStart - WEEK_START_HOUR) * HOUR_ROW_HEIGHT,
    height: Math.max((clampedEnd - clampedStart) * HOUR_ROW_HEIGHT, 34),
  };
}

function isPastEvent(event: NormalizedCalendarEvent): boolean {
  return event.endAt < new Date();
}

function positionWeekEvents(events: NormalizedCalendarEvent[]): PositionedWeekEvent[] {
  const sorted = [...events].sort((left, right) => {
    const byStart = left.startAt.getTime() - right.startAt.getTime();
    if (byStart !== 0) {
      return byStart;
    }
    return right.endAt.getTime() - left.endAt.getTime();
  });

  const positioned: PositionedWeekEvent[] = [];
  let cluster: NormalizedCalendarEvent[] = [];
  let clusterEnd = 0;

  const flushCluster = () => {
    if (cluster.length === 0) {
      return;
    }

    const columnEnds: number[] = [];
    const assignments = new Map<string, number>();

    for (const event of cluster) {
      const start = event.startAt.getTime();
      const end = event.endAt.getTime();
      let column = columnEnds.findIndex((columnEnd) => columnEnd <= start);

      if (column === -1) {
        column = columnEnds.length;
        columnEnds.push(end);
      } else {
        columnEnds[column] = end;
      }

      assignments.set(event.id, column);
    }

    const columnCount = Math.max(columnEnds.length, 1);
    for (const event of cluster) {
      const layout = getWeekEventLayout(event);
      const column = assignments.get(event.id) ?? 0;
      positioned.push({
        event,
        top: layout.top,
        height: layout.height,
        leftPercent: (column / columnCount) * 100,
        widthPercent: 100 / columnCount,
      });
    }

    cluster = [];
    clusterEnd = 0;
  };

  for (const event of sorted) {
    const start = event.startAt.getTime();
    const end = event.endAt.getTime();

    if (cluster.length > 0 && start >= clusterEnd) {
      flushCluster();
    }

    cluster.push(event);
    clusterEnd = Math.max(clusterEnd, end);
  }

  flushCluster();
  return positioned;
}

function EventEditorModal({
  state,
  timezone,
  onClose,
  onChange,
  onSave,
  onDelete,
}: {
  state: Exclude<EventEditorState, { mode: "closed" }>;
  timezone: string;
  onClose: () => void;
  onChange: (field: keyof EventDraft, value: string) => void;
  onSave: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="dashboard-modal-backdrop fixed inset-0 z-[120] flex items-center justify-center bg-calm-primary/35 px-4 py-6 backdrop-blur-sm">
      <div className="dashboard-modal glass-panel w-full max-w-2xl rounded-[2rem] p-6 md:p-7">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Schedule editor</p>
            <h2 className="display-font mt-2 text-3xl font-semibold text-white">
              {state.mode === "create" ? "Create event" : "Edit event"}
            </h2>
            <p className="mt-2 text-sm leading-7 text-calm-muted">
              Save changes directly to your Google Calendar.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-[rgba(255,255,255,0.06)] bg-white/80 px-3 py-2 text-sm text-calm-muted transition hover:bg-[rgba(255,255,255,0.05)]"
          >
            Close
          </button>
        </div>

        {state.error && (
          <div className="mt-5 rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-900">
            {state.error}
          </div>
        )}

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="md:col-span-2">
            <span className="mb-2 block text-sm font-semibold text-calm-text">Title</span>
            <input
              value={state.draft.title}
              onChange={(event) => onChange("title", event.target.value)}
              className="w-full rounded-2xl border border-[rgba(255,255,255,0.06)] bg-transparent text-white px-4 py-3 text-sm text-calm-text outline-none transition focus:border-ember"
              placeholder="Team sync"
            />
          </label>

          <label>
            <span className="mb-2 block text-sm font-semibold text-calm-text">Start</span>
            <input
              type="datetime-local"
              value={state.draft.startAt}
              onChange={(event) => onChange("startAt", event.target.value)}
              className="w-full rounded-2xl border border-[rgba(255,255,255,0.06)] bg-transparent text-white px-4 py-3 text-sm text-calm-text outline-none transition focus:border-ember"
            />
          </label>

          <label>
            <span className="mb-2 block text-sm font-semibold text-calm-text">End</span>
            <input
              type="datetime-local"
              value={state.draft.endAt}
              onChange={(event) => onChange("endAt", event.target.value)}
              className="w-full rounded-2xl border border-[rgba(255,255,255,0.06)] bg-transparent text-white px-4 py-3 text-sm text-calm-text outline-none transition focus:border-ember"
            />
          </label>

          <label>
            <span className="mb-2 block text-sm font-semibold text-calm-text">Location</span>
            <input
              value={state.draft.location}
              onChange={(event) => onChange("location", event.target.value)}
              className="w-full rounded-2xl border border-[rgba(255,255,255,0.06)] bg-transparent text-white px-4 py-3 text-sm text-calm-text outline-none transition focus:border-ember"
              placeholder="Zoom or office"
            />
          </label>

          <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-transparent px-4 py-3">
            <p className="text-sm font-semibold text-calm-text">Timezone</p>
            <p className="mt-1 text-sm text-calm-muted opacity-80">{timezone}</p>
          </div>

          <label className="md:col-span-2">
            <span className="mb-2 block text-sm font-semibold text-calm-text">Description</span>
            <textarea
              rows={4}
              value={state.draft.description}
              onChange={(event) => onChange("description", event.target.value)}
              className="w-full resize-none rounded-2xl border border-[rgba(255,255,255,0.06)] bg-transparent text-white px-4 py-3 text-sm text-calm-text outline-none transition focus:border-ember"
              placeholder="Agenda or notes"
            />
          </label>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            {state.mode === "edit" && (
              <button
                type="button"
                onClick={onDelete}
                disabled={state.deleting || state.submitting}
                className="rounded-full border border-red-500/20 bg-red-500/5 px-4 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-100 disabled:cursor-wait disabled:opacity-70"
              >
                {state.deleting ? "Deleting..." : "Delete"}
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-[rgba(255,255,255,0.06)] bg-white/80 px-4 py-2 text-sm font-medium text-calm-text transition hover:bg-[rgba(255,255,255,0.05)]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onSave}
              disabled={state.submitting || state.deleting}
              className="rounded-full bg-calm-primary px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:bg-[rgba(255,255,255,0.02)]0"
            >
              {state.submitting ? "Saving..." : state.mode === "create" ? "Create event" : "Save changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ScheduleWorkspace({
  view,
  onViewChange,
  hasGoogleCalendar,
  timezone,
  refreshKey,
  onPaywall,
}: ScheduleWorkspaceProps) {
  const [anchorDate, setAnchorDate] = useState(() => new Date());
  const [events, setEvents] = useState<NormalizedCalendarEvent[]>([]);
  const [loading, setLoading] = useState(hasGoogleCalendar);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [editorState, setEditorState] = useState<EventEditorState>({ mode: "closed" });
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [dragSavingEventId, setDragSavingEventId] = useState<string | null>(null);
  const [ignoredConflicts, setIgnoredConflicts] = useState<Set<string>>(new Set());
  const weekBoardRef = useRef<HTMLDivElement | null>(null);

  const conflictEventIds = useMemo(() => {
    const overlaps = new Set<string>();
    for (let i = 0; i < events.length; i++) {
      for (let j = i + 1; j < events.length; j++) {
        const a = events[i];
        const b = events[j];
        if (a.isAllDay || b.isAllDay) continue;
        if (a.startAt < b.endAt && b.startAt < a.endAt) {
          if (!ignoredConflicts.has(a.id)) overlaps.add(a.id);
          if (!ignoredConflicts.has(b.id)) overlaps.add(b.id);
        }
      }
    }
    return overlaps;
  }, [events, ignoredConflicts]);

  const quickDeleteEvent = async (id: string) => {
    setEvents((cur) => cur.filter((e) => e.id !== id));
    try {
      await deleteCalendarEvent(id);
    } catch {
      /* ignore */
    }
  };

  const resolvedTimezone = timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const weekDays = useMemo(() => buildWeekDays(anchorDate), [anchorDate]);
  const monthDays = useMemo(() => buildMonthGrid(anchorDate), [anchorDate]);
  const timeLabels = useMemo(
    () =>
      Array.from({ length: WEEK_END_HOUR - WEEK_START_HOUR }, (_, index) => {
        const date = new Date();
        date.setHours(WEEK_START_HOUR + index, 0, 0, 0);
        return date;
      }),
    [],
  );

  const loadEvents = useCallback(async () => {
    if (!hasGoogleCalendar) {
      setEvents([]);
      setError(null);
      setLoading(false);
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const items = await fetchCalendarEvents();
      const normalized = items
        .map(normalizeEvent)
        .filter((item): item is NormalizedCalendarEvent => item !== null)
        .sort((left, right) => left.startAt.getTime() - right.startAt.getTime());
      setEvents(normalized);
    } catch (error: unknown) {
      if (error instanceof ApiError || error instanceof Error) {
        setError(error.message);
      } else {
        setError("Failed to load Google Calendar events.");
      }
    } finally {
      setLoading(false);
    }
  }, [hasGoogleCalendar]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents, refreshKey]);

  const refreshEvents = useCallback(async () => {
    setRefreshing(true);
    await loadEvents();
    setRefreshing(false);
  }, [loadEvents]);

  const weekTimedEventsByDay = useMemo(() => {
    const groups = new Map<string, NormalizedCalendarEvent[]>();
    for (const event of events) {
      if (event.isAllDay) {
        continue;
      }
      const key = getDateKey(event.startAt);
      const current = groups.get(key) ?? [];
      current.push(event);
      groups.set(key, current);
    }
    return groups;
  }, [events]);

  const weekAllDayEventsByDay = useMemo(() => {
    const groups = new Map<string, NormalizedCalendarEvent[]>();
    for (const event of events) {
      if (!event.isAllDay) {
        continue;
      }
      const startDay = cloneDate(event.startAt);
      const endDay = cloneDate(event.endAt);
      if (endDay > startDay) {
        endDay.setDate(endDay.getDate() - 1);
      }

      for (
        let currentDay = cloneDate(startDay);
        currentDay <= endDay;
        currentDay = addDays(currentDay, 1)
      ) {
        const key = getDateKey(currentDay);
        const current = groups.get(key) ?? [];
        current.push(event);
        groups.set(key, current);
      }
    }
    return groups;
  }, [events]);

  const monthEventsByDay = useMemo(() => {
    const groups = new Map<string, NormalizedCalendarEvent[]>();
    for (const event of events) {
      const startDay = cloneDate(event.startAt);
      const endDay = cloneDate(event.endAt);
      if (event.isAllDay && endDay > startDay) {
        endDay.setDate(endDay.getDate() - 1);
      }

      for (
        let currentDay = cloneDate(startDay);
        currentDay <= endDay;
        currentDay = addDays(currentDay, 1)
      ) {
        const key = getDateKey(currentDay);
        const current = groups.get(key) ?? [];
        current.push(event);
        groups.set(key, current);
      }
    }
    return groups;
  }, [events]);

  const periodLabel = useMemo(() => {
    if (view === "week") {
      const weekStart = startOfWeek(anchorDate);
      const weekEnd = addDays(weekStart, 6);
      return `${weekRangeFormatter.format(weekStart)} - ${weekRangeFormatter.format(weekEnd)}`;
    }
    return monthFormatter.format(anchorDate);
  }, [anchorDate, view]);

  const visibleEventCount = useMemo(() => {
    const days = view === "week" ? weekDays : monthDays;
    const map = view === "week" ? weekTimedEventsByDay : monthEventsByDay;
    return days.reduce((count, day) => count + (map.get(getDateKey(day))?.length ?? 0), 0);
  }, [monthDays, monthEventsByDay, view, weekDays, weekTimedEventsByDay]);

  const currentTimeLine = useMemo(() => {
    if (view !== "week") {
      return null;
    }
    const now = new Date();
    const dayIndex = weekDays.findIndex((day) => isSameDay(day, now));
    const hourValue = now.getHours() + now.getMinutes() / 60;

    if (dayIndex < 0 || hourValue < WEEK_START_HOUR || hourValue > WEEK_END_HOUR) {
      return null;
    }

    return {
      dayIndex,
      top: (hourValue - WEEK_START_HOUR) * HOUR_ROW_HEIGHT,
    };
  }, [view, weekDays]);

  const shiftPeriod = (direction: -1 | 1) => {
    setAnchorDate((current) => {
      const next = new Date(current);
      if (view === "week") {
        next.setDate(next.getDate() + direction * 7);
      } else {
        next.setMonth(next.getMonth() + direction);
      }
      return next;
    });
  };

  const connectGoogleCalendar = async () => {
    const url = await getGoogleAuthUrl();
    window.location.href = url;
  };

  const openCreateEditor = (date: Date) => {
    setEditorState({
      mode: "create",
      draft: defaultDraft(date),
      error: null,
      submitting: false,
      deleting: false,
    });
  };

  const openEditEditor = (event: NormalizedCalendarEvent) => {
    const draft = draftFromEvent(event);
    setEditorState({
      mode: "edit",
      event,
      originalDraft: draft,
      draft,
      error: null,
      submitting: false,
      deleting: false,
    });
  };

  const persistDraggedEvent = useCallback(
    async (state: DragState) => {
      const durationMs = state.event.endAt.getTime() - state.event.startAt.getTime();
      const updatedEvent: NormalizedCalendarEvent = {
        ...state.event,
        startAt: state.currentStartAt,
        endAt: new Date(state.currentStartAt.getTime() + durationMs),
      };

      setEvents((current) =>
        current.map((item) => (item.id === updatedEvent.id ? updatedEvent : item)),
      );
      setDragSavingEventId(updatedEvent.id);

      try {
        await updateCalendarEvent(updatedEvent.id, {
          start_at: updatedEvent.startAt.toISOString(),
          end_at: updatedEvent.endAt.toISOString(),
          timezone: resolvedTimezone,
        });
        await refreshEvents();
    } catch (error: unknown) {
      if (isPaywallError(error)) {
        onPaywall?.(error.payload);
      }
      setEvents((current) =>
        current.map((item) => (item.id === state.event.id ? state.event : item)),
      );
      setError(
          isPaywallError(error)
            ? error.payload.message
            : error instanceof ApiError || error instanceof Error
            ? error.message
            : "Failed to move the event.",
      );
      } finally {
        setDragSavingEventId(null);
      }
    },
    [onPaywall, refreshEvents, resolvedTimezone],
  );

  const startWeekDrag = (
    pointerEvent: ReactPointerEvent<HTMLDivElement>,
    event: NormalizedCalendarEvent,
    originDayIndex: number,
  ) => {
    pointerEvent.preventDefault();
    pointerEvent.stopPropagation();

    setDragState({
      event,
      originDayIndex,
      originStartMinutes: getMinutesSinceMidnight(event.startAt),
      currentDayIndex: originDayIndex,
      currentStartAt: event.startAt,
      currentEndAt: event.endAt,
      startClientX: pointerEvent.clientX,
      startClientY: pointerEvent.clientY,
      moved: false,
    });
  };

  useEffect(() => {
    if (!dragState || view !== "week") {
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      const board = weekBoardRef.current;
      if (!board) {
        return;
      }

      const rect = board.getBoundingClientRect();
      const dayWidth = (rect.width - TIME_COLUMN_WIDTH) / 7;
      const durationMinutes = Math.max(
        Math.round((dragState.event.endAt.getTime() - dragState.event.startAt.getTime()) / 60000),
        DRAG_SNAP_MINUTES,
      );
      const latestStartMinutes = Math.max(
        WEEK_START_HOUR * 60,
        WEEK_END_HOUR * 60 - durationMinutes,
      );

      const dayOffset = Math.round((event.clientX - dragState.startClientX) / dayWidth);
      const currentDayIndex = clamp(dragState.originDayIndex + dayOffset, 0, 6);

      const minuteOffset =
        Math.round(
          (event.clientY - dragState.startClientY) /
          ((HOUR_ROW_HEIGHT / 60) * DRAG_SNAP_MINUTES),
        ) * DRAG_SNAP_MINUTES;
      const currentMinutes = clamp(
        dragState.originStartMinutes + minuteOffset,
        WEEK_START_HOUR * 60,
        latestStartMinutes,
      );

      const currentStartAt = buildDateForDayAndMinutes(weekDays[currentDayIndex], currentMinutes);
      const currentEndAt = new Date(currentStartAt.getTime() + durationMinutes * 60000);

      setDragState((current) =>
        current
          ? {
            ...current,
            currentDayIndex,
            currentStartAt,
            currentEndAt,
            moved:
              current.moved ||
              Math.abs(event.clientX - dragState.startClientX) > 6 ||
              Math.abs(event.clientY - dragState.startClientY) > 6,
          }
          : current,
      );
    };

    const handlePointerUp = () => {
      const state = dragState;
      setDragState(null);

      if (!state.moved) {
        openEditEditor(state.event);
        return;
      }

      void persistDraggedEvent(state);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [dragState, openEditEditor, persistDraggedEvent, view, weekDays]);

  const closeEditor = () => {
    setEditorState({ mode: "closed" });
  };

  const updateEditorDraft = (field: keyof EventDraft, value: string) => {
    setEditorState((current) => {
      if (current.mode === "closed") {
        return current;
      }
      return {
        ...current,
        draft: {
          ...current.draft,
          [field]: value,
        },
        error: null,
      };
    });
  };

  const saveEditor = async () => {
    if (editorState.mode === "closed") {
      return;
    }

    const startDate = parseInputDateTime(editorState.draft.startAt);
    const endDate = parseInputDateTime(editorState.draft.endAt);
    const title = editorState.draft.title.trim();

    if (!title) {
      setEditorState((current) =>
        current.mode === "closed" ? current : { ...current, error: "Title is required." },
      );
      return;
    }

    if (!startDate || !endDate) {
      setEditorState((current) =>
        current.mode === "closed"
          ? current
          : { ...current, error: "Start and end time are required." },
      );
      return;
    }

    if (endDate <= startDate) {
      setEditorState((current) =>
        current.mode === "closed"
          ? current
          : { ...current, error: "End time must be after the start time." },
      );
      return;
    }

    setEditorState((current) =>
      current.mode === "closed" ? current : { ...current, submitting: true, error: null },
    );

    try {
      if (editorState.mode === "create") {
        const payload: CalendarEventInput = {
          title,
          description: editorState.draft.description.trim() || null,
          location: editorState.draft.location.trim() || null,
          start_at: startDate.toISOString(),
          end_at: endDate.toISOString(),
          timezone: resolvedTimezone,
          reminders: [15],
        };
        await createCalendarEvent(payload);
      } else {
        const payload: CalendarEventUpdateInput = {};
        const original = editorState.originalDraft;

        if (!equalDraftValue(editorState.draft.title, original.title)) {
          payload.title = title;
        }
        if (!equalDraftValue(editorState.draft.description, original.description)) {
          payload.description = editorState.draft.description.trim() || null;
        }
        if (!equalDraftValue(editorState.draft.location, original.location)) {
          payload.location = editorState.draft.location.trim() || null;
        }
        if (editorState.draft.startAt !== original.startAt) {
          payload.start_at = startDate.toISOString();
          payload.timezone = resolvedTimezone;
        }
        if (editorState.draft.endAt !== original.endAt) {
          payload.end_at = endDate.toISOString();
          payload.timezone = resolvedTimezone;
        }

        if (Object.keys(payload).length === 0) {
          closeEditor();
          return;
        }

        await updateCalendarEvent(editorState.event.id, payload);
      }

      await refreshEvents();
      closeEditor();
    } catch (error: unknown) {
      if (isPaywallError(error)) {
        onPaywall?.(error.payload);
      }
      const message =
        isPaywallError(error)
          ? error.payload.message
          : error instanceof ApiError || error instanceof Error
          ? error.message
          : "Failed to save the event.";

      setEditorState((current) =>
        current.mode === "closed"
          ? current
          : { ...current, submitting: false, error: message },
      );
    }
  };

  const removeEvent = async () => {
    if (editorState.mode !== "edit") {
      return;
    }

    setEditorState((current) =>
      current.mode === "edit" ? { ...current, deleting: true, error: null } : current,
    );

    try {
      await deleteCalendarEvent(editorState.event.id);
      await refreshEvents();
      closeEditor();
    } catch (error: unknown) {
      if (isPaywallError(error)) {
        onPaywall?.(error.payload);
      }
      const message =
        isPaywallError(error)
          ? error.payload.message
          : error instanceof ApiError || error instanceof Error
          ? error.message
          : "Failed to delete the event.";

      setEditorState((current) =>
        current.mode === "edit"
          ? { ...current, deleting: false, error: message }
          : current,
      );
    }
  };

  const weekBodyHeight = (WEEK_END_HOUR - WEEK_START_HOUR) * HOUR_ROW_HEIGHT;
  const timezoneLabel = formatTimezoneLabel(resolvedTimezone);

  return (
    <>
      <section className="dashboard-calendar glass-panel flex min-h-[760px] flex-col overflow-hidden rounded-[2rem]">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] px-5 py-4 md:px-6">
          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-full border border-[rgba(255,255,255,0.06)] bg-transparent text-white p-1">
              {(["week", "month"] as CalendarView[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => onViewChange(option)}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${option === view ? "bg-calm-primary text-white" : "text-calm-muted hover:bg-[rgba(255,255,255,0.05)]"
                    }`}
                >
                  {option === "week" ? "Weekly" : "Monthly"}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={() => shiftPeriod(-1)}
              className="rounded-full border border-[rgba(255,255,255,0.06)] bg-transparent px-4 py-2 text-sm font-medium text-calm-text transition hover:bg-[rgba(255,255,255,0.05)]"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setAnchorDate(new Date())}
              className="rounded-full bg-calm-primary px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => shiftPeriod(1)}
              className="rounded-full border border-[rgba(255,255,255,0.06)] bg-transparent px-4 py-2 text-sm font-medium text-calm-text transition hover:bg-[rgba(255,255,255,0.05)]"
            >
              Next
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(255,255,255,0.05)] px-4 py-2 text-sm font-semibold text-white">
              {periodLabel}
            </span>
            <span className="rounded-full border border-[rgba(255,255,255,0.06)] bg-white/80 px-4 py-2 text-sm text-calm-muted">
              {visibleEventCount} events
            </span>
            <button
              type="button"
              onClick={() => openCreateEditor(anchorDate)}
              className="rounded-full bg-[#2563d8] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#1f57c1]"
            >
              New event
            </button>
            <button
              type="button"
              onClick={refreshEvents}
              className="rounded-full border border-[rgba(255,255,255,0.06)] bg-transparent text-white px-4 py-2 text-sm font-medium text-calm-text transition hover:bg-[rgba(255,255,255,0.05)]"
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        {!hasGoogleCalendar ? (
          <div className="flex flex-1 items-center justify-center p-8">
            <div className="max-w-xl rounded-[1.75rem] border border-amber-500/20 bg-amber-500/5 p-8 text-center">
              <p className="eyebrow !text-amber-700">Google Calendar</p>
              <h2 className="display-font mt-3 text-3xl font-semibold text-amber-100">
                Connect your calendar to unlock the full schedule view
              </h2>
              <p className="mt-4 text-sm leading-7 text-amber-200/80">
                This board renders your real Google Calendar data and lets you create or edit
                events directly from the dashboard.
              </p>
              <button
                type="button"
                onClick={() => void connectGoogleCalendar()}
                className="mt-6 rounded-full bg-amber-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-amber-700"
              >
                Connect Google Calendar
              </button>
            </div>
          </div>
        ) : loading ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-ink border-t-transparent" />
              <p className="mt-4 text-sm text-calm-muted">Loading your Google Calendar...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex flex-1 items-center justify-center p-8">
            <div className="max-w-xl rounded-[1.75rem] border border-red-500/20 bg-red-500/5 p-8 text-center">
              <p className="eyebrow !text-red-700">Calendar error</p>
              <h2 className="mt-3 text-2xl font-semibold text-red-100">
                We could not load events from Google Calendar
              </h2>
              <p className="mt-3 text-sm leading-7 text-red-200/80">{error}</p>
              <button
                type="button"
                onClick={refreshEvents}
                className="mt-6 rounded-full bg-red-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-red-700"
              >
                Try again
              </button>
            </div>
          </div>
        ) : view === "week" ? (
          <div className="dashboard-week-view flex-1 overflow-hidden relative">
            {visibleEventCount === 0 && !loading && (
              <div className="absolute inset-0 z-50 flex items-center justify-center pointer-events-none">
                <div className="dashboard-empty-state max-w-sm text-center pointer-events-auto">
                  <h3 className="text-calm-text font-bold text-lg">Your schedule is empty.</h3>
                  <p className="text-calm-muted text-sm mt-2">Tell me what you want to plan using the AI panel, or click anywhere to add an event.</p>
                </div>
              </div>
            )}
            <div className="dashboard-calendar-scroll h-full overflow-auto">
              <div
                ref={weekBoardRef}
                className="relative min-w-[1120px]"
                style={{
                  display: "grid",
                  gridTemplateColumns: `${TIME_COLUMN_WIDTH}px repeat(7, minmax(0, 1fr))`,
                  gridTemplateRows: `${HEADER_HEIGHT}px ${ALL_DAY_HEIGHT}px ${weekBodyHeight}px`,
                }}
              >
                <div className="border-b border-[rgba(255,255,255,0.06)] bg-transparent px-3 py-5 text-sm font-medium text-calm-muted">
                  {timezoneLabel}
                </div>

                {weekDays.map((day) => {
                  const isToday = isSameDay(day, new Date());
                  const dayKey = getDateKey(day);
                  const allDayEvents = weekAllDayEventsByDay.get(dayKey) ?? [];

                  return (
                    <div
                      key={`header-${dayKey}`}
                      className="border-b border-[rgba(255,255,255,0.06)] bg-transparent px-4 py-3"
                    >
                      <div className="flex h-full flex-col items-center justify-center gap-1">
                        <span
                          className={`text-sm font-semibold uppercase tracking-[0.18em] ${isToday ? "text-[#2563d8]" : "text-calm-muted"
                            }`}
                        >
                          {weekdayFormatter.format(day)}
                        </span>
                        <span
                          className={`flex h-14 w-14 items-center justify-center rounded-full text-2xl font-medium ${isToday
                            ? "bg-[#2563d8] text-white"
                            : "text-white"
                            }`}
                        >
                          {dayNumberFormatter.format(day)}
                        </span>
                        <button
                          type="button"
                          onClick={() => openCreateEditor(day)}
                          className="text-[11px] font-semibold uppercase tracking-[0.14em] text-calm-muted opacity-70 transition hover:text-white"
                        >
                          Add
                        </button>
                        {allDayEvents.length > 0 && (
                          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-calm-muted opacity-70">
                            {allDayEvents.length} all-day
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}

                <div className="border-b border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)]" />

                {weekDays.map((day) => {
                  const allDayEvents = weekAllDayEventsByDay.get(getDateKey(day)) ?? [];
                  return (
                    <div
                      key={`allday-${getDateKey(day)}`}
                      className="border-b border-[rgba(255,255,255,0.06)] border-l border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.01)] px-2 py-1"
                    >
                      <div className="flex gap-1 overflow-x-auto">
                        {allDayEvents.slice(0, 2).map((event) => (
                          <button
                            key={event.id}
                            type="button"
                            onClick={() => openEditEditor(event)}
                            className={`min-w-0 rounded-full px-3 py-1 text-xs font-medium transition ${isPastEvent(event)
                              ? "bg-[rgba(255,255,255,0.05)] text-calm-muted opacity-70 line-through hover:bg-[rgba(255,255,255,0.05)]"
                              : "bg-[rgba(255,255,255,0.05)] text-calm-text hover:bg-[rgba(255,255,255,0.08)]"
                              }`}
                          >
                            <span className="block whitespace-normal break-words">{event.title}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}

                <div className="relative border-r border-[rgba(255,255,255,0.06)] bg-transparent">
                  {timeLabels.map((time) => (
                    <div
                      key={`time-${time.getHours()}`}
                      className="absolute left-0 right-0 border-t border-[rgba(255,255,255,0.06)] px-2 pt-1 text-right text-sm text-calm-muted"
                      style={{ top: (time.getHours() - WEEK_START_HOUR) * HOUR_ROW_HEIGHT }}
                    >
                      {hourLabelFormatter.format(time)}
                    </div>
                  ))}
                </div>

                {weekDays.map((day, columnIndex) => {
                  const timedEvents = (weekTimedEventsByDay.get(getDateKey(day)) ?? []).filter(
                    (event) => event.id !== dragState?.event.id,
                  );
                  const positionedEvents = positionWeekEvents(timedEvents);
                  const draggedEventForColumn =
                    dragState && dragState.currentDayIndex === columnIndex ? dragState : null;

                  return (
                    <div
                      key={`column-${getDateKey(day)}`}
                      className="relative border-l border-[rgba(255,255,255,0.06)]"
                      style={{
                        backgroundImage:
                          "repeating-linear-gradient(to bottom, transparent 0, transparent 75px, rgba(17, 33, 45, 0.12) 75px, rgba(17, 33, 45, 0.12) 76px)",
                      }}
                    >
                      {Array.from({ length: WEEK_END_HOUR - WEEK_START_HOUR }, (_, index) => {
                        const slotDate = new Date(day);
                        slotDate.setHours(WEEK_START_HOUR + index, 0, 0, 0);

                        return (
                          <button
                            key={`slot-${getDateKey(day)}-${index}`}
                            type="button"
                            onClick={() => openCreateEditor(slotDate)}
                            className="absolute left-0 right-0 border-t border-transparent transition hover:bg-[rgba(255,255,255,0.02)]"
                            style={{
                              top: index * HOUR_ROW_HEIGHT,
                              height: HOUR_ROW_HEIGHT,
                            }}
                          />
                        );
                      })}

                      {positionedEvents.map((positionedEvent) => {
                        const { event } = positionedEvent;
                        const isPast = isPastEvent(event);
                        const isConflict = conflictEventIds.has(event.id);
                        return (
                          <div
                            key={event.id}
                            role="button"
                            tabIndex={0}
                            onPointerDown={(pointerEvent) =>
                              startWeekDrag(pointerEvent, event, columnIndex)
                            }
                            onKeyDown={(keyEvent) => {
                              if (keyEvent.key === "Enter" || keyEvent.key === " ") {
                                keyEvent.preventDefault();
                                openEditEditor(event);
                              }
                            }}
                            className={`absolute z-10 select-none overflow-hidden touch-none ${dragSavingEventId === event.id ? "cursor-wait opacity-60" : "cursor-pointer"
                              } ${isPast ? "opacity-60" : ""}`}
                            style={{
                              top: positionedEvent.top + 4,
                              height: Math.max(positionedEvent.height - 8, 28),
                              left: `calc(${positionedEvent.leftPercent}% + 0.5rem)`,
                              width: `calc(${positionedEvent.widthPercent}% - 0.75rem)`,
                            }}
                          >
                            <EventCard
                              id={event.id}
                              title={event.title}
                              startTime={formatTimeRange(event).split(' - ')[0]}
                              endTime={formatTimeRange(event).split(' - ')[1] || ""}
                              type={event.title?.toLowerCase().includes('study') ? 'study' : (event.title?.toLowerCase().includes('work') || event.title?.toLowerCase().includes('sync') ? 'work' : (event.title?.toLowerCase().includes('lunch') ? 'personal' : 'default'))}
                              isConflict={isConflict}
                              onEdit={() => openEditEditor(event)}
                              onDelete={() => quickDeleteEvent(event.id)}
                              onMove={() => { }}
                              onResolveConflict={(id) => {
                                // Simple auto resolution logic
                                const startCopy = new Date(event.startAt);
                                startCopy.setHours(startCopy.getHours() + 1);
                                const endCopy = new Date(startCopy);
                                endCopy.setMinutes(startCopy.getMinutes() + ((event.endAt.getTime() - event.startAt.getTime()) / 60000));
                                setEvents((cur) => cur.map((e) => e.id === id ? { ...e, startAt: startCopy, endAt: endCopy } : e));
                                updateCalendarEvent(id, {
                                  start_at: startCopy.toISOString(),
                                  end_at: endCopy.toISOString(),
                                  timezone: resolvedTimezone
                                });
                              }}
                              onIgnoreConflict={(id) => {
                                setIgnoredConflicts((prev) => { const n = new Set(prev); n.add(id); return n; });
                              }}
                              className="w-full h-full border-none shadow-[0_8px_20px_rgba(37,99,216,0.14)]"
                            />
                          </div>
                        );
                      })}

                      {draggedEventForColumn && (() => {
                        const evt = {
                          ...draggedEventForColumn.event,
                          startAt: draggedEventForColumn.currentStartAt,
                          endAt: draggedEventForColumn.currentEndAt,
                        };
                        return (
                          <div
                            className="pointer-events-none absolute left-2 right-2 z-30 touch-none shadow-[0_14px_30px_rgba(37,99,216,0.2)]"
                            style={{
                              top: getWeekEventLayout(evt).top + 4,
                              height: Math.max(getWeekEventLayout(evt).height - 8, 28),
                            }}
                          >
                            <EventCard
                              id={evt.id}
                              title={evt.title}
                              startTime={formatTimeRange(evt).split(' - ')[0]}
                              endTime={formatTimeRange(evt).split(' - ')[1] || ""}
                              type={evt.title?.toLowerCase().includes('study') ? 'study' : (evt.title?.toLowerCase().includes('work') || evt.title?.toLowerCase().includes('sync') ? 'work' : (evt.title?.toLowerCase().includes('lunch') ? 'personal' : 'default'))}
                              className="w-full h-full opacity-80 border-calm-primary/50"
                            />
                          </div>
                        );
                      })()}

                      {currentTimeLine && currentTimeLine.dayIndex === columnIndex && (
                        <div
                          className="pointer-events-none absolute left-0 right-0 z-20"
                          style={{ top: currentTimeLine.top }}
                        >
                          <div className="absolute -left-2 top-[-6px] h-3 w-3 rounded-full bg-red-500/50" />
                          <div className="h-[2px] bg-red-500/50" />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          <div className="dashboard-month-view flex-1 overflow-hidden">
            <div className="dashboard-calendar-scroll h-full overflow-auto p-3 md:p-4">
              <div className="grid min-w-[980px] grid-cols-7 overflow-hidden rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-transparent">
                {Array.from({ length: 7 }, (_, index) => (
                  <div
                    key={`month-label-${index}`}
                    className="border-b border-[rgba(255,255,255,0.06)] px-3 py-4 text-center text-sm font-semibold uppercase tracking-[0.18em] text-calm-muted opacity-80"
                  >
                    {weekdayFormatter.format(addDays(startOfWeek(new Date()), index))}
                  </div>
                ))}

                {monthDays.map((day) => {
                  const dayKey = getDateKey(day);
                  const dayEvents = monthEventsByDay.get(dayKey) ?? [];
                  const isToday = isSameDay(day, new Date());
                  const inActiveMonth = day.getMonth() === anchorDate.getMonth();

                  return (
                    <div
                      key={dayKey}
                      onClick={() => openCreateEditor(day)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openCreateEditor(day);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      className={`relative min-h-[162px] cursor-pointer border-r border-t border-[rgba(255,255,255,0.06)] px-3 py-3 text-left align-top transition hover:bg-[rgba(255,255,255,0.02)] focus:outline-none focus:ring-2 focus:ring-[#2563d8]/20 ${inActiveMonth ? "bg-transparent text-white" : "bg-transparent"
                        }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={`flex h-10 w-10 items-center justify-center rounded-full text-lg font-medium ${isToday
                            ? "bg-[#2563d8] text-white"
                            : inActiveMonth
                              ? "text-white"
                              : "text-calm-muted opacity-70"
                            }`}
                        >
                          {dayNumberFormatter.format(day)}
                        </span>
                        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-calm-muted opacity-70">
                          {longWeekdayFormatter.format(day)}
                        </span>
                      </div>

                      <div className="mt-3 space-y-2">
                        {dayEvents.slice(0, 4).map((event) => (
                          <div
                            key={event.id}
                            className={`rounded-xl px-2.5 py-2 text-xs ${isPastEvent(event)
                              ? "bg-[rgba(255,255,255,0.05)]/70 text-calm-muted opacity-70"
                              : "bg-[rgba(255,255,255,0.05)] text-calm-text"
                              }`}
                          >
                            <button
                              type="button"
                              onClick={(eventClick) => {
                                eventClick.stopPropagation();
                                openEditEditor(event);
                              }}
                              className="w-full text-left"
                            >
                              <p className={`whitespace-normal break-words font-semibold ${isPastEvent(event) ? "text-calm-muted opacity-70 line-through" : "text-white"}`}>
                                {event.title}
                              </p>
                              <p className={`mt-1 whitespace-normal break-words text-[11px] uppercase tracking-[0.14em] ${isPastEvent(event) ? "text-calm-muted opacity-70 line-through" : "text-calm-muted opacity-80"}`}>
                                {formatTimeRange(event)}
                              </p>
                            </button>
                          </div>
                        ))}

                        {dayEvents.length > 4 && (
                          <div className="text-xs font-medium text-calm-muted opacity-80">
                            +{dayEvents.length - 4} more
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </section>

      {editorState.mode !== "closed" && (
        <EventEditorModal
          state={editorState}
          timezone={resolvedTimezone}
          onClose={closeEditor}
          onChange={updateEditorDraft}
          onSave={() => void saveEditor()}
          onDelete={() => void removeEvent()}
        />
      )}
    </>
  );
}
