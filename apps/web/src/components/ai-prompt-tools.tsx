"use client";

import type { RefObject } from "react";
import type { UploadedFileResponse } from "@/lib/api";

type AiPromptToolsProps = {
  attachments: UploadedFileResponse[];
  fileInputRef: RefObject<HTMLInputElement | null>;
  uploading: boolean;
  uploadProgress: number | null;
  recording: boolean;
  transcribing: boolean;
  error: string | null;
  disabled?: boolean;
  onFilesSelected: (files: File[]) => void;
  onOpenFilePicker: () => void;
  onRemoveAttachment: (id: string) => void;
  onToggleRecording: () => void;
};

function PaperclipIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 1 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <path d="M12 19v3" />
    </svg>
  );
}

export function AiPromptTools({
  attachments,
  disabled,
  error,
  fileInputRef,
  onFilesSelected,
  onOpenFilePicker,
  onRemoveAttachment,
  onToggleRecording,
  recording,
  transcribing,
  uploading,
  uploadProgress,
}: AiPromptToolsProps) {
  return (
    <div className="space-y-2">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        multiple
        accept="image/*,.pdf,.txt,.md,text/plain,application/pdf"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length > 0) onFilesSelected(files);
          event.target.value = "";
        }}
      />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onOpenFilePicker}
          disabled={disabled || uploading}
          className="inline-flex min-h-9 items-center gap-2 rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-3 text-xs font-extrabold text-[rgba(35,25,66,0.72)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          title="Attach a file or image"
        >
          <PaperclipIcon />
          {uploading ? `Uploading${uploadProgress !== null ? ` ${uploadProgress}%` : ""}` : "Attach"}
        </button>
        <button
          type="button"
          onClick={onToggleRecording}
          disabled={disabled || transcribing}
          className={`inline-flex min-h-9 items-center gap-2 rounded-xl border px-3 text-xs font-extrabold transition disabled:cursor-not-allowed disabled:opacity-50 ${
            recording
              ? "border-red-500/30 bg-red-500/10 text-red-700"
              : "border-[rgba(20,184,166,0.18)] bg-white/70 text-[rgba(35,25,66,0.72)] hover:bg-white"
          }`}
          title="Voice input"
        >
          <MicIcon />
          {recording ? "Stop" : transcribing ? "Transcribing" : "Voice"}
        </button>
        <span className="text-xs font-semibold text-[rgba(60,44,96,0.46)]">Paste images with Ctrl+V</span>
      </div>

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {attachments.map((attachment) => (
            <span
              key={attachment.id}
              className="inline-flex max-w-full items-center gap-2 rounded-xl border border-[rgba(20,184,166,0.18)] bg-[rgba(20,184,166,0.08)] px-3 py-2 text-xs font-bold text-[rgba(35,25,66,0.72)]"
            >
              <span className="max-w-[180px] truncate">{attachment.filename}</span>
              <button
                type="button"
                onClick={() => onRemoveAttachment(attachment.id)}
                className="text-[rgba(35,25,66,0.46)] transition hover:text-red-600"
                aria-label={`Remove ${attachment.filename}`}
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}

      {error && <p className="text-xs font-bold text-red-700">{error}</p>}
    </div>
  );
}
