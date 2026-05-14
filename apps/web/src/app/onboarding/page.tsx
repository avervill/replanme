"use client";

import { useRouter } from "next/navigation";
import { AuthGuard } from "@/components/auth-guard";
import { OnboardingFlow } from "@/components/onboarding/OnboardingFlow";
import { useAuth } from "@/lib/auth";

function OnboardingPageContent() {
  const router = useRouter();
  const { user } = useAuth();

  if (!user) return null;

  return (
    <main className="landing-page min-h-screen">
      <OnboardingFlow
        user={user}
        mode="settings"
        onClose={() => router.replace("/dashboard")}
        onFinished={() => router.replace("/dashboard")}
      />
    </main>
  );
}

export default function OnboardingPage() {
  return (
    <AuthGuard>
      <OnboardingPageContent />
    </AuthGuard>
  );
}
