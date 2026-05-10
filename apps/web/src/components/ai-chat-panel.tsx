"use client";

import { KeyboardEvent, useEffect, useRef, useState, FormEvent } from "react";
import { isPaywallError, sendAssistantMessage, fetchChatHistory, clearChatHistory, type AssistantResponse, type PaywallPayload } from "@/lib/api";
import { ensureStringMessage } from "@/lib/assistant-message";
import { useAuth } from "@/lib/auth";
import type { CalendarView } from "@/components/schedule-workspace";

type AiChatPanelProps = {
  timeframe: CalendarView;
  onCollapse?: () => void;
  onCalendarChanged?: () => void;
  onPaywall?: (payload: PaywallPayload) => void;
};

type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  text: string;
  actions?: Array<{ kind: string; summary: string }>;
  pendingText?: string; // e.g. "Thinking...", "Planning your week..."
  awaitingConfirmation?: boolean;
  confirmationToken?: string | null;
};

const SESSION_STORAGE_KEY = "replanme_assistant_session";

const starterMessage: ChatMessage = {
  id: 1,
  role: "assistant",
  text: "Tell me what you want to plan for this week.",
};

const getPendingText = (input: string) => {
  const lower = input.toLowerCase();
  if (lower.includes("conflict") || lower.includes("overlap") || lower.includes("fix")) {
    return "Resolving conflicts...";
  }
  if (lower.includes("plan") || lower.includes("week")) {
    return "Planning your week...";
  }
  return "Thinking...";
};

export function AiChatPanel({ timeframe, onCollapse, onCalendarChanged, onPaywall }: AiChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([starterMessage]);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const { refresh } = useAuth();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let nextId = "";
    const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) {
      nextId = existing;
    } else {
      nextId = crypto.randomUUID();
      window.localStorage.setItem(SESSION_STORAGE_KEY, nextId);
    }
    setSessionId(nextId);

    setLoadingHistory(true);
    fetchChatHistory(nextId)
      .then((data) => {
        if (data.messages && data.messages.length > 0) {
          const historyMessages: ChatMessage[] = data.messages.map((m, index) => ({
            id: index + 1000, // offset IDs to avoid conflict with starter message
            role: m.role,
            text: m.text,
          }));
          setMessages([starterMessage, ...historyMessages]);
        }
      })
      .catch((err) => {
        console.error("Failed to load chat history:", err);
      })
      .finally(() => {
        setLoadingHistory(false);
      });
  }, []);

  useEffect(() => {
    if (viewportRef.current) {
      viewportRef.current.scrollTop = viewportRef.current.scrollHeight;
    }
  }, [messages]);

  const sendPrompt = async (promptValue: string) => {
    const prompt = promptValue.trim();
    if (!prompt || submitting) return;

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      text: prompt,
    };

    const pendingMessageId = Date.now() + 1;
    const pendingText = getPendingText(prompt);

    setMessages((current) => [
      ...current,
      userMessage,
      {
        id: pendingMessageId,
        role: "assistant",
        text: "",
        pendingText,
      },
    ]);
    setInput("");
    setSubmitting(true);

    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const activeSessionId = sessionId || crypto.randomUUID();

      const response = await sendAssistantMessage({
        prompt,
        timezone,
        session_id: activeSessionId,
        preview: false,
      });

      if (response.status === "completed") {
        onCalendarChanged?.();
      }
      if (response.status !== "failed") {
        void refresh();
      }

      setMessages((current) =>
        current.map((msg) =>
          msg.id === pendingMessageId
            ? {
              ...msg,
              text: ensureStringMessage(response.reply),
              pendingText: undefined,
              actions: response.display_actions.length > 0
                ? response.display_actions.map((action) => ({
                  kind: ensureStringMessage(action.kind),
                  summary: ensureStringMessage(action.summary),
                }))
                : undefined,
              awaitingConfirmation: response.awaiting_confirmation,
              confirmationToken: response.confirmation_token,
            }
            : msg
        )
      );
    } catch (error: unknown) {
      if (isPaywallError(error)) {
        onPaywall?.(error.payload);
      }
      setMessages((current) =>
        current.map((msg) =>
          msg.id === pendingMessageId
            ? {
              ...msg,
              text: isPaywallError(error)
                ? error.payload.message
                : error instanceof Error
                  ? error.message
                  : "I couldn't process that.",
              pendingText: undefined,
            }
            : msg
        )
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmation = async (messageId: number) => {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    const confirmationToken = messages.find((msg) => msg.id === messageId)?.confirmationToken ?? null;
    setMessages((current) =>
      current.map((msg) =>
        msg.id === messageId
          ? { ...msg, pendingText: "Executing changes...", awaitingConfirmation: false }
          : msg
      )
    );

    try {
      const response = await sendAssistantMessage({
        prompt: "yes",
        timezone,
        session_id: sessionId,
        preview: false,
        confirm: Boolean(confirmationToken),
        confirmation_token: confirmationToken,
      });

      if (response.status === "completed") {
        onCalendarChanged?.();
      }
      if (response.status !== "failed") {
        void refresh();
      }

      setMessages((current) =>
        current.map((msg) =>
          msg.id === messageId
            ? {
              ...msg,
              text: ensureStringMessage(response.reply),
              pendingText: undefined,
              awaitingConfirmation: response.awaiting_confirmation,
              confirmationToken: response.confirmation_token,
            }
            : msg
        )
      );
    } catch (error) {
      if (isPaywallError(error)) {
        onPaywall?.(error.payload);
      }
      setMessages((current) =>
        current.map((msg) =>
          msg.id === messageId
            ? {
              ...msg,
              text: isPaywallError(error) ? error.payload.message : "Failed to confirm changes.",
              pendingText: undefined
            }
            : msg
        )
      );
    }
  };

  const handlePromptKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendPrompt(input);
  };

  return (
    <aside className="dashboard-chat-panel">
      <div className="dashboard-chat-header">
        <div className="flex-1">
          <span className="mini-label">AI assistant</span>
          <h2>Planner chat</h2>
          <p>Ask anything to manage your schedule</p>
        </div>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={async () => {
              if (!sessionId) return;
              try {
                await clearChatHistory(sessionId);
                setMessages([starterMessage]);
              } catch (e) {
                console.error("Failed to clear chat", e);
              }
            }}
            className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
            title="Clear chat and restart session"
          >
            Clear
          </button>
          <button type="button" onClick={onCollapse} className="dashboard-chat-collapse" aria-label="Collapse AI chat">
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5" />
            </svg>
          </button>
        </div>
      </div>

      <div ref={viewportRef} className="dashboard-chat-messages">
        {loadingHistory && (
          <div className="flex justify-center p-6 w-full">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent opacity-50 block mx-auto"></span>
          </div>
        )}
        {!loadingHistory && messages.map((message) => (
          <div
            key={message.id}
            className={`flex flex-col ${message.role === "assistant" ? "items-start pr-10" : "items-end pl-10"
              }`}
          >
            <div
              className={`dashboard-message-bubble ${message.role === "assistant"
                ? "assistant"
                : "user"
                }`}
            >
              {message.pendingText ? (
                <div className="flex items-center gap-2 opacity-75">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current"></span>
                  <span className="italic">{message.pendingText}</span>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{message.text}</p>
              )}
            </div>

            {message.actions && message.actions.length > 0 && !message.pendingText && (
              <div className="mt-2 w-full space-y-2 pl-2">
                {message.actions.map((action, idx) => (
                  <div key={idx} className="dashboard-action-chip">
                    <p>
                      {action.kind.replace(/_/g, " ")}
                    </p>
                    <span>{action.summary}</span>
                  </div>
                ))}
              </div>
            )}

            {message.awaitingConfirmation && !message.pendingText && (
              <div className="mt-3 pl-2">
                <button
                  type="button"
                  onClick={() => void handleConfirmation(message.id)}
                  className="dashboard-apply-button"
                >
                  Apply changes
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <form onSubmit={onSubmit} className="dashboard-chat-form">
        <label htmlFor="planner-prompt" className="sr-only">Message the AI assistant</label>
        <div className="dashboard-input-shell">
          <textarea
            ref={inputRef}
            id="planner-prompt"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handlePromptKeyDown}
            rows={1}
            placeholder="E.g., Move tomorrow's sync to Thursday..."
            className="dashboard-chat-input"
          />
          <button
            type="submit"
            disabled={submitting || !input.trim()}
            className="dashboard-send-button"
            aria-label="Send message"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14m-7-7 7 7-7 7" />
            </svg>
          </button>
        </div>
      </form>
    </aside>
  );
}
