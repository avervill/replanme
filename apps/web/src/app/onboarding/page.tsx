"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

type Step = "goals" | "productivity" | "weekly";

export default function OnboardingPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState<Step>("goals");
  const [isLoading, setIsLoading] = useState(false);
  
  const [formData, setFormData] = useState({
    goal: "",
    productivity: "",
    weeklyGoals: "",
  });

  const goalOptions = [
    { value: "chaotic", label: "Chaotic schedule", description: "Too many meetings, no structure" },
    { value: "focus", label: "Lack of focus", description: "Can't find deep work time" },
    { value: "meetings", label: "Too many meetings", description: "Calendar is overloaded" },
    { value: "procrastination", label: "Procrastination", description: "Hard to prioritize" },
  ];

  const productivityOptions = [
    { value: "morning", label: "Morning", description: "Best focus in the AM" },
    { value: "afternoon", label: "Afternoon", description: "Peak productivity 12-6pm" },
    { value: "evening", label: "Evening", description: "Night owl, late hours" },
  ];

  const handleGoalSelect = (value: string) => {
    setFormData({ ...formData, goal: value });
    setCurrentStep("productivity");
  };

  const handleProductivitySelect = (value: string) => {
    setFormData({ ...formData, productivity: value });
    setCurrentStep("weekly");
  };

  const handleWeeklyGoalsSubmit = async () => {
    if (!formData.weeklyGoals.trim()) {
      alert("Please tell us what matters this week");
      return;
    }

    setIsLoading(true);
    try {
      // Store onboarding data for the AI to use
      const onboardingData = {
        goal: formData.goal,
        productivity: formData.productivity,
        weeklyGoals: formData.weeklyGoals,
      };
      
      localStorage.setItem("onboarding", JSON.stringify(onboardingData));
      
      // TODO: Call AI to generate initial weekly plan
      // For now, just redirect to dashboard
      router.push("/dashboard");
    } catch (error) {
      console.error("Onboarding error:", error);
      alert("Something went wrong. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-calm-dark text-calm-text">
      {/* Header */}
      <div className="border-b border-calm-primary/10 px-4 py-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl">
          <Link href="/" className="text-xl font-bold text-calm-primary">
            replanme
          </Link>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex min-h-[calc(100vh-80px)] items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
        <div className="w-full max-w-2xl">
          {/* Step 1: Goals */}
          {currentStep === "goals" && (
            <div className="animate-fade-in">
              <div className="mb-12 text-center">
                <div className="mb-6 inline-block rounded-full bg-calm-primary/20 px-4 py-2">
                  <span className="text-sm font-semibold text-calm-primary">Step 1 of 3</span>
                </div>
                <h1 className="text-4xl font-bold">What do you want to fix?</h1>
                <p className="mt-3 text-calm-muted">Help us understand your biggest scheduling challenge</p>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {goalOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => handleGoalSelect(option.value)}
                    className="calm-card text-left transition hover:border-calm-primary"
                  >
                    <h3 className="font-bold">{option.label}</h3>
                    <p className="mt-2 text-sm text-calm-muted">{option.description}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Productivity */}
          {currentStep === "productivity" && (
            <div className="animate-fade-in">
              <button
                onClick={() => setCurrentStep("goals")}
                className="mb-6 text-sm text-calm-muted hover:text-calm-text"
              >
                Back
              </button>

              <div className="mb-12 text-center">
                <div className="mb-6 inline-block rounded-full bg-calm-primary/20 px-4 py-2">
                  <span className="text-sm font-semibold text-calm-primary">Step 2 of 3</span>
                </div>
                <h1 className="text-4xl font-bold">When do you feel most productive?</h1>
                <p className="mt-3 text-calm-muted">We'll protect your best hours for deep work</p>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                {productivityOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => handleProductivitySelect(option.value)}
                    className="calm-card text-center transition hover:border-calm-secondary"
                  >
                    <h3 className="font-bold">{option.label}</h3>
                    <p className="mt-2 text-sm text-calm-muted">{option.description}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 3: Weekly Goals */}
          {currentStep === "weekly" && (
            <div className="animate-fade-in">
              <button
                onClick={() => setCurrentStep("productivity")}
                className="mb-6 text-sm text-calm-muted hover:text-calm-text"
              >
                Back
              </button>

              <div className="mb-12 text-center">
                <div className="mb-6 inline-block rounded-full bg-calm-primary/20 px-4 py-2">
                  <span className="text-sm font-semibold text-calm-primary">Step 3 of 3</span>
                </div>
                <h1 className="text-4xl font-bold">What matters this week?</h1>
                <p className="mt-3 text-calm-muted">Describe your priorities and we'll build your schedule</p>
              </div>

              <div className="space-y-4">
                <textarea
                  value={formData.weeklyGoals}
                  onChange={(e) => setFormData({ ...formData, weeklyGoals: e.target.value })}
                  placeholder="E.g., Finish Q2 roadmap, prep for Monday presentation, 3 focus days for coding..."
                  className="w-full rounded-lg border border-calm-primary/20 bg-calm-card px-4 py-3 text-calm-text placeholder-calm-muted/50 focus:border-calm-primary focus:outline-none focus:ring-1 focus:ring-calm-primary"
                  rows={5}
                />
                
                <button
                  onClick={handleWeeklyGoalsSubmit}
                  disabled={isLoading}
                  className={`w-full btn-primary py-3 ${isLoading ? "opacity-50" : ""}`}
                >
                  {isLoading ? "Setting up your schedule..." : "Continue to dashboard"}
                </button>
              </div>

              <p className="mt-6 text-center text-xs text-calm-muted">
                We'll generate your initial weekly plan and you can adjust it in the dashboard.
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
