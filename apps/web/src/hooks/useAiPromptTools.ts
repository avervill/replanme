"use client";

import { useCallback, useRef, useState, type ClipboardEvent } from "react";
import {
  isPaywallError,
  transcribeVoice,
  uploadAssistantFile,
  type PaywallPayload,
  type UploadedFileResponse,
} from "@/lib/api";

type UseAiPromptToolsOptions = {
  onTranscript: (text: string) => void;
  onPaywall?: (payload: PaywallPayload) => void;
};

function fileNameForBlob(blob: Blob) {
  const extension = blob.type.includes("png")
    ? "png"
    : blob.type.includes("jpeg") || blob.type.includes("jpg")
      ? "jpg"
      : blob.type.includes("webp")
        ? "webp"
        : "bin";
  return `pasted-image-${Date.now()}.${extension}`;
}

export function useAiPromptTools({ onTranscript, onPaywall }: UseAiPromptToolsOptions) {
  const [attachments, setAttachments] = useState<UploadedFileResponse[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const handleError = useCallback((err: unknown, fallback: string) => {
    if (isPaywallError(err)) {
      onPaywall?.(err.payload);
    }
    setError(err instanceof Error ? err.message : fallback);
  }, [onPaywall]);

  const uploadFiles = useCallback(async (files: File[] | Blob[]) => {
    const validFiles = files.filter((file) => file.size > 0);
    if (validFiles.length === 0) return;

    setUploading(true);
    setUploadProgress(0);
    setError(null);
    try {
      const uploaded: UploadedFileResponse[] = [];
      for (const file of validFiles) {
        const filename = file instanceof File && file.name ? file.name : fileNameForBlob(file);
        const item = await uploadAssistantFile(file, filename, setUploadProgress);
        uploaded.push(item);
      }
      setAttachments((current) => [...current, ...uploaded]);
    } catch (err) {
      handleError(err, "Could not upload the file.");
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  }, [handleError]);

  const handlePaste = useCallback((event: ClipboardEvent<HTMLTextAreaElement>) => {
    const images: File[] = [];
    for (const item of Array.from(event.clipboardData.items)) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) images.push(file);
      }
    }
    if (images.length > 0) {
      event.preventDefault();
      void uploadFiles(images);
    }
  }, [uploadFiles]);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const removeAttachment = useCallback((id: string) => {
    setAttachments((current) => current.filter((item) => item.id !== id));
  }, []);

  const clearAttachments = useCallback(() => {
    setAttachments([]);
  }, []);

  const toggleRecording = useCallback(async () => {
    setError(null);
    if (recorderRef.current && recording) {
      recorderRef.current.stop();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Voice input is not available in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        setTranscribing(true);
        try {
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
          const result = await transcribeVoice(blob);
          if (result.transcript.trim()) {
            onTranscript(result.transcript.trim());
          }
        } catch (err) {
          handleError(err, "Could not transcribe the voice input.");
        } finally {
          setTranscribing(false);
          recorderRef.current = null;
          chunksRef.current = [];
        }
      };

      recorder.start();
      setRecording(true);
    } catch (err) {
      handleError(err, "Microphone access failed.");
      setRecording(false);
    }
  }, [handleError, onTranscript, recording]);

  return {
    attachments,
    clearAttachments,
    error,
    fileInputRef,
    handlePaste,
    openFilePicker,
    recording,
    removeAttachment,
    setError,
    toggleRecording,
    transcribing,
    uploadFiles,
    uploading,
    uploadProgress,
  };
}
