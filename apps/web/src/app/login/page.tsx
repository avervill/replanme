"use client";

import { useEffect, useState } from "react";
import { getGoogleAuthUrl, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

function GoogleIcon() {
  return (
    <svg aria-hidden="true" width="19" height="19" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="currentColor" opacity="0.8" />
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="currentColor" opacity="0.9" />
      <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="currentColor" opacity="0.7" />
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="currentColor" />
    </svg>
  );
}

export default function LoginPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [user, loading, router]);

  useEffect(() => {
    getGoogleAuthUrl()
      .then((url) => {
        setAuthUrl(url);
        setAuthError(null);
      })
      .catch((error: unknown) => {
        setAuthUrl(null);
        if (error instanceof ApiError || error instanceof Error) {
          setAuthError(error.message);
          return;
        }
        setAuthError("Failed to load Google sign-in. Check the API configuration and try again.");
      });
  }, []);

  return (
    <main className="landing-page login-page">
      <span className="login-decor login-decor-one" />
      <span className="login-decor login-decor-two" />
      <span className="login-decor login-decor-three" />

      <section className="login-shell reveal">
        <div className="login-card">
          <span className="hero-badge">Connect your calendar</span>
          <h1>Welcome to replanme</h1>
          <p>Choose a calendar to start planning calmer weeks with AI.</p>

          {authError ? (
            <div className="login-error" role="alert">
              <strong>Connection error</strong>
              <span>{authError}</span>
            </div>
          ) : null}

          <div className="login-provider-list">
            <a href={authUrl ?? "#"} className={`login-provider-button google ${authUrl ? "" : "loading"}`} aria-disabled={!authUrl}>
              <span className="provider-icon">
                <GoogleIcon />
              </span>
              {authUrl ? "Connect Google Calendar" : "Loading Google Calendar..."}
            </a>

            <button type="button" className="login-provider-button outlook" disabled>
              <span className="provider-icon outlook-icon">O</span>
              Connect Outlook Calendar
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
