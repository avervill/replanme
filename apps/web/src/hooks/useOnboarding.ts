"use client";

import { useCallback, useEffect, useState } from "react";
import {
  completeOnboarding,
  fetchOnboardingStatus,
  saveOnboarding,
  skipOnboarding,
  type OnboardingData,
  type OnboardingStatus,
  type UploadedFileResponse,
} from "@/lib/api";

export const PENDING_INITIAL_PROMPT_KEY = "replanme_pending_initial_prompt";
export const PENDING_INITIAL_PROMPT_ID_KEY = "replanme_pending_initial_prompt_id";
export const PENDING_INITIAL_ATTACHMENTS_KEY = "replanme_pending_initial_attachments";

export function useOnboarding(enabled = true) {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return null;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOnboardingStatus();
      setStatus(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load onboarding status.");
      return null;
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const save = useCallback(async (data: OnboardingData) => {
    const next = await saveOnboarding(data);
    setStatus(next);
    return next;
  }, []);

  const complete = useCallback(async () => {
    const next = await completeOnboarding();
    setStatus(next);
    return next;
  }, []);

  const skip = useCallback(async () => {
    const next = await skipOnboarding();
    setStatus(next);
    return next;
  }, []);

  return {
    status,
    loading,
    error,
    refresh,
    save,
    complete,
    skip,
    shouldShowOnboarding: Boolean(status && status.onboardingCompleted !== true),
  };
}

export function storePendingInitialPrompt(prompt: string, attachments: UploadedFileResponse[] = []) {
  const trimmed = prompt.trim();
  if (!trimmed || typeof window === "undefined") return;
  window.localStorage.setItem(PENDING_INITIAL_PROMPT_KEY, trimmed);
  window.localStorage.setItem(PENDING_INITIAL_PROMPT_ID_KEY, crypto.randomUUID());
  window.localStorage.setItem(PENDING_INITIAL_ATTACHMENTS_KEY, JSON.stringify(attachments));
}
