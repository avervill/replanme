"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createEventFromPrompt,
  type PlannerAction,
} from "@/lib/api";
import type { CalendarView } from "@/components/schedule-workspace";

type AiChatPanelProps = {
  timeframe: CalendarView;
  onCalendarChanged?: () => void;
};

type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  text: string;
  actions?: PlannerAction[];
  pending?: boolean;
};

const starterMessage: ChatMessage = {
  id: 1,
  role: "assistant",
  text: "Tell me what to add to your calendar. Example: Meeting with Sarah tomorrow at 14:00 for 45 minutes.",
};

export function AiChatPanel({ timeframe, onCalendarChanged }: AiChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([starterMessage]);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    viewport.scrollTop = viewport.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const textarea = inputRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 140)}px`;
  }, [input]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const prompt = input.trim();
    if (!prompt || submitting) {
      return;
    }

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      text: prompt,
    };
    const pendingMessageId = Date.now() + 1;

    setMessages((current) => [
      ...current,
      userMessage,
      {
        id: pendingMessageId,
        role: "assistant",
        text: "Extracting the event and adding it to Google Calendar...",
        pending: true,
      },
    ]);
    setInput("");
    setSubmitting(true);

    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const response = await createEventFromPrompt({
        prompt,
        timezone,
      });

      if (response.created) {
        onCalendarChanged?.();
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === pendingMessageId
            ? {
                ...message,
                text: response.message,
                actions: response.created
                  ? (response.events.length > 0 ? response.events : response.event ? [response.event] : []).map(
                      (event) => ({
                        kind: "create_event",
                        summary: `${event.title} was added to Google Calendar.`,
                      }),
                    )
                  : [
                      {
                        kind: "ask_user",
                        summary: response.message,
                      },
                    ],
                pending: false,
              }
            : message,
        ),
      );
    } catch (error: unknown) {
      const text =
        error instanceof ApiError || error instanceof Error
          ? error.message
          : "The planning assistant could not respond.";

      setMessages((current) =>
        current.map((message) =>
          message.id === pendingMessageId
            ? {
                ...message,
                text,
                pending: false,
              }
            : message,
        ),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="glass-panel self-start bg-white/88 xl:sticky xl:top-[5rem] xl:h-[calc(100vh-6rem)] xl:max-h-[calc(100vh-6rem)] flex min-h-[720px] flex-col overflow-hidden rounded-[2.25rem]">
      <div className="border-b border-black/5 px-6 py-6 md:px-7">
        <h2 className="display-font text-[2.25rem] font-semibold leading-none text-ink">
          AI assistant
        </h2>
      </div>

      <div ref={viewportRef} className="flex-1 space-y-3 overflow-y-auto bg-white/78 px-5 py-5 md:px-6">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`rounded-[1.35rem] px-4 py-3 text-sm leading-6 ${
              message.role === "assistant"
                ? "mr-4 bg-white text-slate-700 shadow-[0_14px_28px_rgba(17,33,45,0.06)]"
                : "ml-8 bg-ink text-white"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-bold uppercase tracking-[0.24em] opacity-55">
                {message.role}
              </span>
              {message.pending && (
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-45">
                  working
                </span>
              )}
            </div>

            <p className="mt-2 whitespace-pre-wrap">{message.text}</p>

            {message.actions && message.actions.length > 0 && (
              <div className="mt-4 space-y-2">
                {message.actions.map((action, actionIndex) => (
                  <div
                    key={`${message.id}-${action.kind}-${actionIndex}`}
                    className="rounded-2xl border border-black/5 bg-slate-50 px-3 py-3 text-slate-700"
                  >
                    <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                      {action.kind.replaceAll("_", " ")}
                    </p>
                    <p className="mt-1 text-sm leading-6">{action.summary}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <form onSubmit={onSubmit} className="border-t border-black/5 bg-white/88 p-4 md:p-5">
        <label htmlFor="planner-prompt" className="sr-only">
          Ask the planning assistant
        </label>
        <div className="flex items-end gap-2 rounded-[1.75rem] border border-black/10 bg-white px-3 py-3 transition focus-within:border-ember">
          <button
            type="button"
            aria-label="Attach file"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-lg font-semibold text-slate-600 transition hover:bg-slate-200"
          >
            +
          </button>
          <textarea
            ref={inputRef}
            id="planner-prompt"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            rows={1}
            placeholder={`Example: Add a ${timeframe} planning meeting tomorrow at 10:00 for 45 minutes.`}
            className="max-h-[140px] min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-5 text-slate-700 outline-none"
          />
          <button
            type="button"
            aria-label="Voice input"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600 transition hover:bg-slate-200"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <path
                d="M19 11a7 7 0 0 1-14 0M12 18v4M8 22h8"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="ml-auto rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:bg-slate-500"
          >
            {submitting ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </aside>
  );
}
