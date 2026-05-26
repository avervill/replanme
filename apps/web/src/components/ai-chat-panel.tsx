"use client";

import { KeyboardEvent, useEffect, useRef, useState, FormEvent } from "react";
import { isPaywallError, sendAssistantMessage, fetchChatHistory, clearChatHistory, type PaywallPayload, type UploadedFileResponse } from "@/lib/api";
import { ensureStringMessage } from "@/lib/assistant-message";
import { useAuth } from "@/lib/auth";
import { PENDING_INITIAL_ATTACHMENTS_KEY, PENDING_INITIAL_PROMPT_ID_KEY, PENDING_INITIAL_PROMPT_KEY } from "@/hooks/useOnboarding";
import { useAiPromptTools } from "@/hooks/useAiPromptTools";
import { AiPromptTools } from "@/components/ai-prompt-tools";
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
  attachments?: UploadedFileResponse[];
};

const SESSION_STORAGE_KEY = "replanme_assistant_session";
const CHAT_HISTORY_TIMEOUT_MS = 3500;

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

const readPendingInitialAttachments = () => {
  try {
    const raw = window.localStorage.getItem(PENDING_INITIAL_ATTACHMENTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed as UploadedFileResponse[] : [];
  } catch {
    return [];
  }
};

export function AiChatPanel({ timeframe, onCollapse, onCalendarChanged, onPaywall }: AiChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([starterMessage]);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const { refresh } = useAuth();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const consumedInitialPromptRef = useRef<string | null>(null);
  const hasLocalActivityRef = useRef(false);
  const promptTools = useAiPromptTools({
    onTranscript: (text) => setInput((current) => (current.trim() ? `${current.trim()} ${text}` : text)),
    onPaywall,
  });

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

    let cancelled = false;
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      if (!cancelled) setLoadingHistory(false);
    }, CHAT_HISTORY_TIMEOUT_MS);

    setLoadingHistory(true);
    fetchChatHistory(nextId)
      .then((data) => {
        if (cancelled || timedOut || hasLocalActivityRef.current) return;
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
        window.clearTimeout(timeoutId);
        if (!cancelled) setLoadingHistory(false);
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, []);

  useEffect(() => {
    if (viewportRef.current) {
      viewportRef.current.scrollTop = viewportRef.current.scrollHeight;
    }
  }, [messages]);

  const sendPrompt = async (
    promptValue: string,
    options?: { restoreOnError?: boolean; attachments?: UploadedFileResponse[] },
  ) => {
    const sentAttachments = options?.attachments ?? promptTools.attachments;
    const typedPrompt = promptValue.trim();
    const prompt = typedPrompt || (sentAttachments.length > 0 ? "Please analyze the attached file or image and help me plan from it." : "");
    if (!prompt || submitting || promptTools.uploading) return;

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      text: typedPrompt || prompt,
      attachments: sentAttachments,
    };

    const pendingMessageId = Date.now() + 1;
    const pendingText = getPendingText(prompt);

    hasLocalActivityRef.current = true;
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
    if (!options?.attachments) {
      promptTools.clearAttachments();
    }
    setSubmitting(true);

    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const activeSessionId = sessionId || crypto.randomUUID();

      const response = await sendAssistantMessage({
        prompt,
        timezone,
        session_id: activeSessionId,
        preview: false,
        attachments: sentAttachments,
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
      if (options?.restoreOnError) {
        setInput(typedPrompt);
        inputRef.current?.focus();
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

  useEffect(() => {
    if (loadingHistory || submitting || !sessionId) return;
    const prompt = window.localStorage.getItem(PENDING_INITIAL_PROMPT_KEY);
    const promptId = window.localStorage.getItem(PENDING_INITIAL_PROMPT_ID_KEY) || prompt;
    if (!prompt || !promptId || consumedInitialPromptRef.current === promptId) return;
    const attachments = readPendingInitialAttachments();

    consumedInitialPromptRef.current = promptId;
    window.localStorage.removeItem(PENDING_INITIAL_PROMPT_KEY);
    window.localStorage.removeItem(PENDING_INITIAL_PROMPT_ID_KEY);
    window.localStorage.removeItem(PENDING_INITIAL_ATTACHMENTS_KEY);

    void sendPrompt(prompt, { restoreOnError: true, attachments });
  }, [loadingHistory, sessionId, submitting]);

  const handleConfirmation = async (messageId: number) => {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    const confirmationToken = messages.find((msg) => msg.id === messageId)?.confirmationToken ?? null;
    hasLocalActivityRef.current = true;
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
                hasLocalActivityRef.current = true;
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
          <div className="flex w-full items-center justify-center px-4 py-2 text-xs font-semibold text-calm-muted">
            Loading chat history...
          </div>
        )}
        {messages.map((message) => (
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

            {message.attachments && message.attachments.length > 0 && !message.pendingText && (
              <div className="mt-2 flex flex-wrap gap-2 pl-2">
                {message.attachments.map((attachment) => (
                  <span key={attachment.id} className="rounded-xl border border-[rgba(124,58,237,0.12)] bg-white/70 px-3 py-1 text-xs font-bold text-[rgba(60,44,96,0.62)]">
                    {attachment.filename}
                  </span>
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
            onPaste={promptTools.handlePaste}
            onKeyDown={handlePromptKeyDown}
            rows={1}
            placeholder="E.g., Move tomorrow's sync to Thursday..."
            className="dashboard-chat-input"
          />
          <button
            type="submit"
            disabled={submitting || promptTools.uploading || (!input.trim() && promptTools.attachments.length === 0)}
            className="dashboard-send-button"
            aria-label="Send message"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14m-7-7 7 7-7 7" />
            </svg>
          </button>
        </div>
        <AiPromptTools
          attachments={promptTools.attachments}
          disabled={submitting}
          error={promptTools.error}
          fileInputRef={promptTools.fileInputRef}
          onFilesSelected={(files) => void promptTools.uploadFiles(files)}
          onOpenFilePicker={promptTools.openFilePicker}
          onRemoveAttachment={promptTools.removeAttachment}
          onToggleRecording={() => void promptTools.toggleRecording()}
          recording={promptTools.recording}
          transcribing={promptTools.transcribing}
          uploading={promptTools.uploading}
          uploadProgress={promptTools.uploadProgress}
        />
      </form>
    </aside>
  );
}
