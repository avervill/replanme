import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  title: "replanme — AI Calendar Planner for Smarter Weekly Scheduling",
  description:
    "replanme is an AI-powered calendar planner that connects to Google Calendar and turns your goals, tasks, voice notes, and schedule photos into a realistic weekly plan.",
  keywords: [
    "AI calendar",
    "AI scheduling",
    "weekly planner",
    "Google Calendar AI",
    "AI planner",
    "voice-to-calendar",
    "photo-to-calendar",
    "energy-based scheduling",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    title: "replanme — Plan your week with AI",
    description:
      "Connect Google Calendar, tell AI what matters, and let replanme build a realistic schedule around your goals, energy, and deadlines.",
    url: siteUrl,
    siteName: "replanme",
    type: "website",
  },
};

const navLinks = [
  { href: "#product", label: "Product" },
  { href: "#features", label: "Features" },
  { href: "#faq", label: "FAQ" },
];

const painCards = [
  {
    title: "Planning takes too long",
    text: "You know what you need to do, but turning everything into a clean weekly schedule takes 30-60 minutes every week.",
  },
  {
    title: "Your calendar doesn't understand priorities",
    text: 'A deadline, a workout, a meeting, and "study later" all look the same. Your calendar stores time, not intention.',
  },
  {
    title: "Manual rescheduling is annoying",
    text: "One cancelled meeting can break the whole day. Then you drag events around manually instead of focusing on what matters.",
  },
  {
    title: "Your energy changes during the day",
    text: "Deep work, admin tasks, meetings, and rest should not be scheduled randomly. replanme plans around when you actually have energy.",
  },
];

const workflowSteps = [
  {
    title: "Connect Google Calendar",
    text: "replanme reads your existing events and understands when you are busy.",
  },
  {
    title: "Tell AI what you need",
    text: 'Type or speak naturally: "I need to prepare for my exam, go to the gym 3 times, and finish my project by Friday."',
  },
  {
    title: "AI creates the plan",
    text: "It breaks work into blocks, chooses good times, adds buffers, and avoids conflicts.",
  },
  {
    title: "Review and adjust",
    text: "You can accept, edit, move, or delete anything manually. AI helps, but it does not take control away from you.",
  },
];

const features = [
  {
    icon: "spark",
    title: "AI Weekly Planning",
    text: "Tell replanme your goals for the week and it turns them into a structured calendar with focus blocks, breaks, buffers, and realistic deadlines.",
    microcopy: "Prepare for exams, finish my project, gym 3 times, keep Sunday free.",
  },
  {
    icon: "calendar",
    title: "Google Calendar Sync",
    text: "Connect your Google Calendar and let replanme read availability, avoid conflicts, create events, move meetings, and keep everything synced.",
    microcopy: "Your existing calendar stays the source of truth. replanme simply makes it smarter.",
  },
  {
    icon: "chat",
    title: "AI Chat Sidebar",
    text: "Ask the assistant to add, move, delete, duplicate, or optimize events without clicking through menus.",
    prompts: [
      "Move all low-priority tasks to next week.",
      "Clear my afternoon for deep work.",
      "Duplicate this week's routine to next week.",
      "Find time for gym before Friday.",
    ],
  },
  {
    icon: "image",
    title: "Photo-to-Calendar",
    text: "Upload or paste a photo of a class timetable, paper schedule, screenshot, or handwritten plan. replanme reads the image and converts it into calendar events.",
    microcopy: "Perfect for students, conference schedules, school timetables, travel plans, and screenshots.",
  },
  {
    icon: "mic",
    title: "Voice-to-Calendar",
    text: "Speak your plan and let AI turn it into editable calendar actions.",
    microcopy:
      'Voice is converted to text first: "Book a study session tomorrow morning, gym after lunch, and remind me to call Alex in the evening."',
  },
  {
    icon: "energy",
    title: "Energy-Based Scheduling",
    text: "Set your peak focus, low-energy, and recovery windows. replanme schedules deep work when you are sharp and admin tasks when your energy is lower.",
    prompts: ["Deep work: 09:00-12:00", "Meetings: 13:00-15:00", "Admin: 15:00-17:00", "Personal time: evening"],
  },
  {
    icon: "refresh",
    title: "Smart rescheduling",
    text: "When plans change, replanme can rebuild your day or week around the new reality.",
    microcopy:
      'Try: "My internship got cancelled today. Remove it and use that time for project work." replanme detects, confirms, and adjusts without repeated questions.',
  },
  {
    icon: "hand",
    title: "Manual Control",
    text: "Drag, drop, rename, resize, and delete events manually whenever you want. AI suggestions are useful, not mandatory.",
    microcopy: "You stay in control. replanme assists, but your calendar is still yours.",
  },
];

const whyPoints = [
  {
    title: "Natural language first",
    text: "You do not need to click through forms. Just say what you want.",
  },
  {
    title: "Built around your energy",
    text: "replanme does not treat every hour equally. It learns when you focus best and schedules accordingly.",
  },
  {
    title: "Works with your real calendar",
    text: "It respects existing events, meetings, deadlines, buffers, travel time, and personal commitments.",
  },
  {
    title: "Flexible, not rigid",
    text: "Plans change. replanme helps you rebuild without manually dragging every event around.",
  },
  {
    title: "You stay in control",
    text: "AI proposes and executes with permission. You can review and adjust every change.",
  },
];

const comparisonRows = [
  ["Stores events", "Yes", "Sometimes", "Yes"],
  ["Understands natural language", "No", "Limited", "Yes"],
  ["Plans full week automatically", "No", "No", "Yes"],
  ["Moves tasks around conflicts", "No", "No", "Yes"],
  ["Uses energy levels", "No", "No", "Yes"],
  ["Imports schedule from photo", "No", "No", "Yes"],
  ["Voice-to-calendar", "Rare", "Rare", "Yes"],
  ["Manual calendar control", "Yes", "No", "Yes"],
  ["AI chat assistant", "No", "Limited", "Yes"],
];

const onboardingCards = [
  {
    question: "What are your main goals this week?",
    options: ["Study for exams", "Finish project", "Exercise", "Prepare presentation", "Reduce chaos"],
  },
  {
    question: "When do you focus best?",
    options: ["Morning", "Afternoon", "Evening", "It depends", "I have no idea, help me find out"],
  },
  {
    question: "What should be protected?",
    options: ["Sleep", "Gym", "Family time", "Deep work", "Weekends", "Evenings"],
  },
  {
    question: "What should AI optimize for?",
    options: ["Productivity", "Balance", "Deadline safety", "Less stress", "Free evenings"],
  },
];

const faqItems = [
  {
    question: "What is replanme?",
    answer:
      "replanme is an AI-powered calendar planner that connects to Google Calendar and helps you schedule tasks, goals, habits, meetings, and deadlines using natural language, voice, and images.",
  },
  {
    question: "Does replanme replace Google Calendar?",
    answer: "No. replanme works with Google Calendar. It adds an AI planning layer on top, so your existing calendar stays useful.",
  },
  {
    question: "Can I manually edit my calendar?",
    answer: "Yes. You can drag, drop, rename, delete, and move events manually. AI helps, but you stay in control.",
  },
  {
    question: "Can AI delete or move my events?",
    answer:
      "Only with clear user intent and, for important actions, confirmation. The product should never unexpectedly change important events without user awareness.",
  },
  {
    question: "What is Photo-to-Calendar?",
    answer:
      "It lets you upload or paste a photo of a timetable, printed schedule, screenshot, or planner page. AI extracts the events and creates calendar entries.",
  },
  {
    question: "Does voice input create events instantly?",
    answer:
      "The best UX is: voice gets transcribed into text first, appears in the chat input, and then the user can edit or send it. This prevents transcription mistakes.",
  },
  {
    question: "Who is replanme for?",
    answer:
      "Students, managers, founders, developers, researchers, and anyone who has tasks, deadlines, routines, and too little patience for manual planning.",
  },
  {
    question: "Is replanme free?",
    answer:
      "There should be a free version for basic planning and a Pro version for advanced AI scheduling, photo import, voice input, and energy-based optimization.",
  },
  {
    question: "What makes replanme different?",
    answer: "Normal calendars store events. replanme helps build and adjust the plan itself.",
  },
];

const footerGroups = [
  { title: "Product", links: ["Features", "Pricing", "FAQ"] },
  { title: "Company", links: ["About", "Contact", "Terms"] },
  { title: "Social", links: ["X / Twitter", "Instagram", "YouTube", "LinkedIn"] },
];

function Icon({ name }: { name: string }) {
  const paths: Record<string, string[]> = {
    spark: ["M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2z", "M19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8L19 17z"],
    calendar: ["M7 3v3M17 3v3M4 9h16M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"],
    chat: ["M5 6.5A3.5 3.5 0 0 1 8.5 3h7A3.5 3.5 0 0 1 19 6.5v4A3.5 3.5 0 0 1 15.5 14H11l-4.5 4v-4A3.5 3.5 0 0 1 3 10.5v-4z"],
    image: ["M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", "M21 16l-5-5-4 4-2-2-5 5"],
    mic: ["M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z", "M5 10v1a7 7 0 0 0 14 0v-1", "M12 18v4", "M8 22h8"],
    energy: ["M13 2L4 14h7l-1 8 10-13h-7l1-7z"],
    refresh: ["M20 7v5h-5", "M4 17v-5h5", "M18.5 9A7 7 0 0 0 6.3 6.3L4 8.6", "M5.5 15A7 7 0 0 0 17.7 17.7L20 15.4"],
    hand: ["M7 11V6a2 2 0 1 1 4 0v5", "M11 10V5a2 2 0 1 1 4 0v6", "M15 11V7a2 2 0 1 1 4 0v8a7 7 0 0 1-14 0v-3a2 2 0 1 1 4 0v2"],
  };

  return (
    <svg aria-hidden="true" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {(paths[name] ?? paths.spark).map((path) => (
        <path key={path} d={path} />
      ))}
    </svg>
  );
}

function SectionIntro({ tag, title, text }: { tag: string; title: string; text?: string }) {
  return (
    <div className="section-intro reveal">
      <p className="section-tag">{tag}</p>
      <h2>{title}</h2>
      {text ? <p>{text}</p> : null}
    </div>
  );
}

function HeroVisual() {
  const events = [
    { time: "09:00", title: "Deep Work: ML Project", className: "event-purple" },
    { time: "11:30", title: "Exam Prep Block", className: "event-teal" },
    { time: "15:30", title: "Admin Tasks", className: "event-lavender" },
    { time: "18:00", title: "Gym + Recovery", className: "event-mint" },
  ];

  return (
    <div className="hero-visual reveal" aria-label="Animated AI calendar preview">
      <div className="visual-glow visual-glow-one" />
      <div className="visual-glow visual-glow-two" />
      <div className="calendar-shell">
        <div className="calendar-topbar">
          <div>
            <span className="mini-label">AI weekly plan</span>
            <strong>May 5-11</strong>
          </div>
        </div>

        <div className="assistant-thread">
          <div className="bubble user-bubble">Plan my week around classes, gym, project work, and exam prep.</div>
          <div className="bubble ai-bubble">Done. I protected your focus hours, added study blocks, moved low-priority tasks, and left recovery time.</div>
        </div>

        <div className="mini-calendar">
          <div className="time-rail">
            {["09:00", "11:30", "15:30", "18:00"].map((time) => (
              <span key={time}>{time}</span>
            ))}
          </div>
          <div className="calendar-grid">
            {events.map((event, index) => (
              <div key={event.title} className={`calendar-event ${event.className}`} style={{ animationDelay: `${0.4 + index * 0.18}s` }}>
                <span>{event.time}</span>
                <strong>{event.title}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="floating-card energy-card">
        <span>Energy Map</span>
        <p>Morning: High focus</p>
        <p>Afternoon: Low energy</p>
        <p>Evening: Flexible</p>
      </div>

      <div className="floating-badge voice-badge">Voice → Calendar</div>
      <div className="floating-badge photo-badge">Photo → Calendar</div>
    </div>
  );
}

function ProductMockup() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri"];
  const blocks = [
    ["Planning", "Deep work", "", "Gym"],
    ["Class", "Project", "Admin", ""],
    ["Research", "", "Review", "Recovery"],
    ["Focus", "Deadline prep", "", "Evening free"],
    ["Meeting", "Build", "Wrap-up", ""],
  ];

  return (
    <div className="product-mockup reveal">
      <div className="dashboard-pane">
        <div className="mockup-header">
          <div>
            <span className="mini-label">Weekly calendar</span>
            <strong>Balanced plan</strong>
          </div>
          <button type="button" aria-label="Calendar view options">Week</button>
        </div>
        <div className="mock-calendar">
          {days.map((day, dayIndex) => (
            <div className="mock-day" key={day}>
              <span>{day}</span>
              {blocks[dayIndex].map((block, blockIndex) => (
                <div key={`${day}-${blockIndex}`} className={block ? "mock-block" : "mock-gap"}>
                  {block}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <aside className="chat-pane" aria-label="AI chat sidebar preview">
        <span className="mini-label">AI assistant</span>
        <div className="chat-message user">I have 12 tasks this week, two deadlines, and I want evenings free. Build a realistic plan.</div>
        <div className="chat-message ai">I created a balanced schedule with 5 focus blocks, 3 admin blocks, 2 review sessions, and protected evenings after 7 PM.</div>
        <div className="change-list">
          {["Focus blocks added", "Deadline prep scheduled", "Low-energy tasks moved to afternoon", "Evening free time protected"].map((change) => (
            <span key={change}>{change}</span>
          ))}
        </div>
      </aside>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      <Script
        id="replanme-structured-data"
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            name: "replanme",
            applicationCategory: "ProductivityApplication",
            operatingSystem: "Web",
            description:
              "AI-powered calendar planner for Google Calendar, weekly scheduling, voice-to-calendar, photo-to-calendar, and energy-based scheduling.",
            url: siteUrl,
          }),
        }}
      />

      <main className="landing-page">
        <header className="landing-header">
          <Link href="#top" className="logo-link" aria-label="replanme home">
            <span className="logo-mark">r</span>
            replanme
          </Link>
          <nav className="landing-nav" aria-label="Landing page navigation">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href}>
                {link.label}
              </a>
            ))}
          </nav>
          <div className="header-actions">
            <Link href="/pricing" className="header-pricing-button">
              Pricing
            </Link>
            <Link href="/login" className="header-cta">
              Sign in
            </Link>
          </div>
        </header>

        <section id="top" className="hero-section section-shell">
          <div className="hero-copy reveal">
            <span className="hero-badge">Your week, planned by AI</span>
            <h1>
              Plan your week in seconds.
              <br />
              Not in another painful Sunday evening.
            </h1>
            <p className="hero-subtitle">
              replanme connects to your Google Calendar, understands your goals, tasks, energy levels, and deadlines, then builds a realistic weekly plan you can actually follow. Type, speak, or upload a schedule photo - your calendar updates automatically.
            </p>
            <div className="hero-actions">
              <Link href="/login" className="primary-button">
                Plan my week with AI
              </Link>
              <a href="#features" className="secondary-button">
                See features
              </a>
            </div>
            <p className="trust-line">Google Calendar sync · Voice input · Photo-to-calendar · You stay in control</p>
          </div>
          <HeroVisual />
        </section>

        <section id="problem" className="section-shell">
          <SectionIntro
            tag="The problem"
            title="Calendars store your plans. They don't help you make them."
            text="Most calendar apps are just empty boxes. You still have to decide what to do, when to do it, how long it will take, what to move, what to protect, and what to sacrifice. That is not planning. That is unpaid project management for your own life."
          />
          <div className="card-grid four">
            {painCards.map((card) => (
              <article className="soft-card reveal" key={card.title}>
                <h3>{card.title}</h3>
                <p>{card.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="solution" className="section-shell tinted-section">
          <SectionIntro
            tag="The solution"
            title="Tell replanme what matters. It builds the schedule."
            text="replanme is an AI scheduling assistant that turns your goals, tasks, deadlines, habits, and existing events into a structured calendar. Instead of manually planning your week, you simply describe what you want to get done. replanme finds realistic time slots, protects focus time, adds buffers, and keeps your schedule flexible."
          />
          <div className="workflow-grid">
            {workflowSteps.map((step, index) => (
              <article className="step-card reveal" key={step.title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="product" className="section-shell">
          <SectionIntro
            tag="Product"
            title="A calendar with an AI brain attached"
            text="replanme combines a clean calendar interface with a side AI assistant. Your schedule stays visual and editable, while the AI handles the boring planning logic in the background."
          />
          <ProductMockup />
        </section>

        <section id="features" className="section-shell">
          <SectionIntro
            tag="Features"
            title="Everything you need to stop fighting your calendar"
            text="Plan, reschedule, import, and optimize your time using natural language, voice, images, and manual control."
          />
          <div className="feature-grid">
            {features.map((feature) => (
              <article className="feature-card reveal" key={feature.title}>
                <div className="feature-card-top">
                  <span className="icon-chip">
                    <Icon name={feature.icon} />
                  </span>
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
                {feature.microcopy ? <div className="microcopy">{feature.microcopy}</div> : null}
                {feature.prompts ? (
                  <div className="prompt-list">
                    {feature.prompts.map((prompt) => (
                      <span key={prompt}>{prompt}</span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>

        <section id="why" className="section-shell">
          <SectionIntro tag="Why replanme" title="Because planning should not feel like a second job" />
          <div className="why-list">
            {whyPoints.map((point) => (
              <article className="why-item reveal" key={point.title}>
                <span />
                <div>
                  <h3>{point.title}</h3>
                  <p>{point.text}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section id="comparison" className="section-shell tinted-section">
          <SectionIntro tag="Comparison" title="Not just another calendar app" />
          <div className="comparison-wrap reveal">
            <table>
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Normal calendar</th>
                  <th>Task manager</th>
                  <th>replanme</th>
                </tr>
              </thead>
              <tbody>
                {comparisonRows.map((row) => (
                  <tr key={row[0]}>
                    {row.map((cell, index) => (
                      <td key={`${row[0]}-${cell}-${index}`} className={index === 3 ? "replanme-col" : undefined}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="supporting-line reveal">Traditional calendars show what you already planned. replanme helps you decide what should happen next.</p>
        </section>

        <section id="personalized-planning" className="section-shell">
          <SectionIntro
            tag="Personalized planning"
            title="Your schedule should understand you first"
            text="Before building your first plan, replanme asks a few simple questions so the AI can create schedules that match your real life instead of generating generic productivity advice."
          />
          <div className="question-grid">
            {onboardingCards.map((card) => (
              <article className="question-card reveal" key={card.question}>
                <h3>{card.question}</h3>
                <div>
                  {card.options.map((option) => (
                    <span key={option}>{option}</span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section id="faq" className="section-shell">
          <SectionIntro tag="FAQ" title="Questions people ask before trusting an AI with their calendar" />
          <div className="faq-list">
            {faqItems.map((item) => (
              <details className="faq-item reveal" key={item.question}>
                <summary>{item.question}</summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="section-shell final-cta-section">
          <div className="final-cta reveal">
            <h2>Stop planning your week by hand.</h2>
            <p>Tell replanme what matters, connect your calendar, and let AI build a schedule that actually fits your life.</p>
            <Link href="/login" className="primary-button">
              Start planning with AI
            </Link>
            <span>Google Calendar required · Early access · Built for realistic weekly planning</span>
          </div>
        </section>

        <footer className="landing-footer">
          <div className="footer-brand">
            <Link href="#top" className="logo-link">
              <span className="logo-mark">r</span>
              replanme
            </Link>
            <p>AI-powered scheduling for people who want their calendar to think before they do.</p>
            <a href="mailto:hello@replanme.com">hello@replanme.com</a>
          </div>
          <div className="footer-links">
            {footerGroups.map((group) => (
              <div key={group.title}>
                <h3>{group.title}</h3>
                {group.links.map((link) => (
                  <a key={link} href={link === "Features" ? "#features" : link === "Pricing" ? "/pricing" : link === "FAQ" ? "#faq" : "#top"}>
                    {link}
                  </a>
                ))}
              </div>
            ))}
          </div>
          <p className="footer-copy">© 2026 replanme. All rights reserved.</p>
        </footer>
      </main>
    </>
  );
}
