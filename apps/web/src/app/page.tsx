import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  title: "Resched.me | AI Calendar Assistant for Weekly and Monthly Planning",
  description:
    "Resched.me is an AI calendar assistant for Google Calendar that helps you plan your week and month, protect focus time, drag to reschedule meetings, and organize life with an intelligent scheduling workspace.",
  keywords: [
    "AI calendar assistant",
    "AI scheduling app",
    "Google Calendar AI",
    "weekly planner",
    "monthly planner",
    "smart calendar",
    "meeting rescheduler",
    "calendar productivity app",
    "AI planner",
    "time blocking app",
  ],
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "Resched.me | AI Calendar Assistant for Weekly and Monthly Planning",
    description:
      "Plan your week and month with AI, connect Google Calendar, protect focus time, and reschedule meetings in one workspace.",
    url: siteUrl,
    siteName: "Resched.me",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Resched.me | AI Calendar Assistant for Weekly and Monthly Planning",
    description:
      "AI-assisted weekly and monthly planning for Google Calendar, focus blocks, and smarter scheduling.",
  },
};

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      name: "Resched.me",
      url: siteUrl,
      sameAs: [],
    },
    {
      "@type": "SoftwareApplication",
      name: "Resched.me",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      url: siteUrl,
      description:
        "AI scheduling software for weekly and monthly planning, Google Calendar management, and intelligent meeting rescheduling.",
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
      featureList: [
        "AI calendar planning",
        "Google Calendar sync",
        "Weekly and monthly schedule views",
        "Drag to reschedule meetings",
        "Focus block planning",
      ],
    },
    {
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "What is Resched.me?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Resched.me is an AI calendar assistant that connects to Google Calendar and helps you plan your week and month, organize meetings, and protect focus time.",
          },
        },
        {
          "@type": "Question",
          name: "Does Resched.me work with Google Calendar?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Yes. Resched.me connects directly to Google Calendar so you can view, create, edit, and reschedule events from one scheduling workspace.",
          },
        },
        {
          "@type": "Question",
          name: "Can I reschedule meetings visually?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Yes. In the weekly schedule view, you can drag events to move them to a different time or day and save those changes back to Google Calendar.",
          },
        },
      ],
    },
  ],
};

const featureCards = [
  {
    title: "AI planning that understands time",
    description:
      "Turn rough ideas into a weekly or monthly schedule without manually juggling every meeting and task.",
  },
  {
    title: "Google Calendar connected",
    description:
      "Read, create, edit, and reschedule real calendar events from a single workspace instead of switching tabs.",
  },
  {
    title: "Weekly and monthly views",
    description:
      "Move between deep weekly planning and higher-level monthly visibility with one click.",
  },
  {
    title: "Drag to reschedule meetings",
    description:
      "Adjust timing visually in the schedule board and push changes back to Google Calendar instantly.",
  },
];

const faqs = [
  {
    question: "Who is Resched.me for?",
    answer:
      "It is built for founders, operators, students, creators, and busy professionals who want a smarter way to plan around real calendar constraints.",
  },
  {
    question: "What makes it different from a normal calendar app?",
    answer:
      "A normal calendar stores events. Resched.me helps decide where those events should go, how to protect focus time, and how to reorganize your schedule when priorities change.",
  },
  {
    question: "Can I still edit things manually?",
    answer:
      "Yes. You can create and edit events directly in the schedule window, and the AI assistant helps you plan without taking control away from you.",
  },
];

export default function LandingPage() {
  return (
    <>
      <Script
        id="resched-me-structured-data"
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />

      <main>
        <section className="relative overflow-hidden px-4 pb-16 pt-6 md:px-6 xl:px-8">
          <div className="mx-auto max-w-[1680px]">
            <header className="glass-panel flex flex-wrap items-center justify-between gap-4 rounded-[2rem] px-5 py-4 md:px-6">
              <Link href="/" className="display-font text-2xl font-semibold text-ink">
                Resched.me
              </Link>

              <nav className="hidden items-center gap-6 text-sm font-medium text-slate-600 lg:flex">
                <a href="#features">Features</a>
                <a href="#how-it-works">How it works</a>
                <a href="#faq">FAQ</a>
              </nav>

              <div className="flex items-center gap-3">
                <Link
                  href="/login"
                  className="rounded-full border border-black/10 bg-white/80 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
                >
                  Sign in
                </Link>
                <Link
                  href="/dashboard"
                  className="rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  Open dashboard
                </Link>
              </div>
            </header>

            <div className="grid gap-8 px-1 pt-8 xl:grid-cols-[1.05fr_0.95fr] xl:items-start">
              <section className="glass-panel rounded-[2.5rem] p-8 md:p-10 xl:p-12">
                <p className="eyebrow">AI Calendar Assistant</p>
                <h1 className="section-title mt-4 max-w-5xl text-ink">
                  Plan your week and month with AI, then move meetings like a real scheduling board.
                </h1>
                <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-600">
                  Resched.me is an AI scheduling app for Google Calendar that helps you build
                  smarter weekly plans, protect focus time, reschedule meetings visually, and
                  manage your time from one unified workspace.
                </p>

                <div className="mt-8 flex flex-wrap gap-4">
                  <Link
                    href="/login"
                    className="rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                  >
                    Connect Google Calendar
                  </Link>
                  <a
                    href="#features"
                    className="rounded-full border border-black/10 bg-white/80 px-6 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
                  >
                    Explore features
                  </a>
                </div>

                <dl className="mt-10 grid gap-4 md:grid-cols-3">
                  <div className="rounded-[1.5rem] bg-white/85 p-5">
                    <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Weekly planning
                    </dt>
                    <dd className="mt-2 text-3xl font-semibold text-ink">1 board</dd>
                  </div>
                  <div className="rounded-[1.5rem] bg-white/85 p-5">
                    <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Calendar sync
                    </dt>
                    <dd className="mt-2 text-3xl font-semibold text-ink">Google-native</dd>
                  </div>
                  <div className="rounded-[1.5rem] bg-white/85 p-5">
                    <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Scheduling control
                    </dt>
                    <dd className="mt-2 text-3xl font-semibold text-ink">AI + manual</dd>
                  </div>
                </dl>
              </section>

              <aside className="glass-panel overflow-hidden rounded-[2.5rem] p-5 md:p-6">
                <div className="rounded-[2rem] border border-black/10 bg-white/90 p-4">
                  <div className="grid grid-cols-[84px_repeat(7,minmax(0,1fr))] overflow-hidden rounded-[1.6rem] border border-black/10">
                    <div className="border-b border-r border-black/10 bg-slate-50 px-3 py-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      GMT+05
                    </div>
                    {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day, index) => (
                      <div
                        key={day}
                        className="border-b border-black/10 bg-slate-50 px-3 py-4 text-center"
                      >
                        <p
                          className={`text-xs font-semibold uppercase tracking-[0.18em] ${
                            index === 0 ? "text-[#2563d8]" : "text-slate-500"
                          }`}
                        >
                          {day}
                        </p>
                        <div
                          className={`mx-auto mt-2 flex h-12 w-12 items-center justify-center rounded-full text-2xl font-medium ${
                            index === 0 ? "bg-[#2563d8] text-white" : "text-ink"
                          }`}
                        >
                          {19 + index}
                        </div>
                      </div>
                    ))}

                    {Array.from({ length: 9 }, (_, row) => (
                      <div key={row} className="contents">
                        <div className="border-r border-t border-black/10 bg-white px-3 py-4 text-sm text-slate-500">
                          {`${row + 11} ${row + 11 < 12 ? "AM" : "PM"}`}
                        </div>
                        {Array.from({ length: 7 }, (_, column) => (
                          <div key={`${row}-${column}`} className="border-t border-black/10 bg-white p-2">
                            {row === 1 && column === 2 && (
                              <div className="rounded-2xl bg-[#2563d8]/10 px-3 py-2 text-xs text-[#2563d8]">
                                Product review
                              </div>
                            )}
                            {row === 4 && column === 4 && (
                              <div className="rounded-2xl bg-[#2563d8]/10 px-3 py-2 text-xs text-[#2563d8]">
                                Focus block
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="mt-4 rounded-[2rem] border border-black/10 bg-ink p-5 text-white">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/60">
                    AI assistant
                  </p>
                  <p className="mt-3 text-lg leading-8">
                    “Build a calmer week, protect morning focus, and keep buffers before
                    meetings.”
                  </p>
                </div>
              </aside>
            </div>
          </div>
        </section>

        <section id="features" className="px-4 py-10 md:px-6 xl:px-8">
          <div className="mx-auto max-w-[1680px]">
            <div className="max-w-3xl">
              <p className="eyebrow">Features</p>
              <h2 className="display-font mt-3 text-4xl font-semibold text-ink md:text-5xl">
                Built for people who need a smarter calendar, not just another calendar app
              </h2>
            </div>

            <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
              {featureCards.map((feature) => (
                <article key={feature.title} className="glass-panel rounded-[2rem] p-6">
                  <h3 className="text-2xl font-semibold text-ink">{feature.title}</h3>
                  <p className="mt-4 text-sm leading-7 text-slate-600">{feature.description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="px-4 py-10 md:px-6 xl:px-8">
          <div className="mx-auto grid max-w-[1680px] gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="glass-panel rounded-[2.25rem] p-8">
              <p className="eyebrow">How It Works</p>
              <h2 className="display-font mt-3 text-4xl font-semibold text-ink">
                One flow from idea to calendar
              </h2>
              <p className="mt-5 text-base leading-8 text-slate-600">
                Start with a goal, let the AI assistant suggest a cleaner schedule, then adjust
                directly in the board and sync it to Google Calendar.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <article className="glass-panel rounded-[2rem] p-6">
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
                  1. Connect
                </p>
                <h3 className="mt-3 text-2xl font-semibold text-ink">Bring in your real calendar</h3>
                <p className="mt-3 text-sm leading-7 text-slate-600">
                  Sync Google Calendar so the plan starts from your actual commitments.
                </p>
              </article>
              <article className="glass-panel rounded-[2rem] p-6">
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
                  2. Plan
                </p>
                <h3 className="mt-3 text-2xl font-semibold text-ink">Ask the AI assistant</h3>
                <p className="mt-3 text-sm leading-7 text-slate-600">
                  Generate a better week or month with focus time, buffers, and cleaner meeting flow.
                </p>
              </article>
              <article className="glass-panel rounded-[2rem] p-6">
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
                  3. Adjust
                </p>
                <h3 className="mt-3 text-2xl font-semibold text-ink">Drag and fine-tune visually</h3>
                <p className="mt-3 text-sm leading-7 text-slate-600">
                  Move meetings, edit events, and keep full control over the final schedule.
                </p>
              </article>
            </div>
          </div>
        </section>

        <section id="faq" className="px-4 py-10 pb-20 md:px-6 xl:px-8">
          <div className="mx-auto max-w-[1680px]">
            <div className="max-w-3xl">
              <p className="eyebrow">FAQ</p>
              <h2 className="display-font mt-3 text-4xl font-semibold text-ink md:text-5xl">
                Questions people ask before they trust a scheduling assistant
              </h2>
            </div>

            <div className="mt-8 grid gap-4 xl:grid-cols-3">
              {faqs.map((faq) => (
                <article key={faq.question} className="glass-panel rounded-[2rem] p-6">
                  <h3 className="text-2xl font-semibold text-ink">{faq.question}</h3>
                  <p className="mt-4 text-sm leading-7 text-slate-600">{faq.answer}</p>
                </article>
              ))}
            </div>

            <div className="glass-panel mt-10 rounded-[2.25rem] p-8 text-center md:p-10">
              <p className="eyebrow">Start Planning</p>
              <h2 className="display-font mt-3 text-4xl font-semibold text-ink md:text-5xl">
                Turn your calendar into a system that actually helps you think
              </h2>
              <p className="mx-auto mt-5 max-w-2xl text-base leading-8 text-slate-600">
                Connect Google Calendar, open the dashboard, and start planning with AI-assisted
                weekly and monthly views.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-4">
                <Link
                  href="/login"
                  className="rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  Sign in with Google
                </Link>
                <Link
                  href="/dashboard"
                  className="rounded-full border border-black/10 bg-white/80 px-6 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
                >
                  View dashboard
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}
