"use client";

import Link from "next/link";
import { ArrowLeft, CheckCircle2, ShieldCheck } from "lucide-react";
import { Brand } from "@/components/brand";
import { beginGoogleLogin } from "@/lib/api";

export default function LoginPage() {
  return (
    <main className="auth-page">
      <aside className="auth-aside">
        <Brand />
        <div className="auth-quote">
          <p style={{ color: "#74d4ca", fontSize: 12, fontWeight: 750, letterSpacing: ".12em", textTransform: "uppercase" }}>A calmer way to plan</p>
          <h1>Your calendar should reflect your capacity—not punish it.</h1>
          <p>Connect an allowlisted Google account to plan, review, and apply calendar changes with explicit approval.</p>
          <div style={{ display: "grid", gap: 11, marginTop: 26, color: "#d7e2ef", fontSize: 13 }}>
            <span style={{ display: "flex", gap: 8 }}><CheckCircle2 size={18} color="#65d1c5" /> Approval first, every time</span>
            <span style={{ display: "flex", gap: 8 }}><CheckCircle2 size={18} color="#65d1c5" /> No automatic calendar writes</span>
          </div>
        </div>
        <span style={{ color: "#8298b1", fontSize: 11 }}>Google OAuth is limited to approved test users.</span>
      </aside>
      <section className="auth-main">
        <div className="auth-card">
          <Brand />
          <h2>Welcome to your week.</h2>
          <p>Sign in with Google to securely connect your primary calendar.</p>
          <button className="google-button" type="button" onClick={() => void beginGoogleLogin()}>
            Continue with Google
          </button>
          <p className="auth-note"><ShieldCheck size={13} style={{ display: "inline", verticalAlign: "-2px", marginRight: 4 }} /> Secure session cookie · Access limited to test users</p>
          <Link href="/demo" style={{ marginTop: 18, display: "flex", alignItems: "center", justifyContent: "center", gap: 6, color: "#2563eb", fontSize: 12, fontWeight: 650 }}>
            <ArrowLeft size={14} /> Explore the demo first
          </Link>
        </div>
      </section>
    </main>
  );
}
