import Link from "next/link";
import {
  ArrowRight,
  Camera,
  CheckCircle2,
  Clock3,
  LockKeyhole,
  MessageSquareText,
  Mic2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { WeekPreview } from "@/components/week-preview";

const workflows = [
  {
    icon: MessageSquareText,
    eyebrow: "AI planning",
    title: "Describe the pressure. Get a workable week.",
    body: "Share deadlines, fixed commitments, and the energy you actually have. Replanme proposes focus blocks without silently changing your calendar.",
    example: "“Plan my stats final around classes and my internship.”",
  },
  {
    icon: Camera,
    eyebrow: "Photo to calendar",
    title: "Turn a timetable into editable events.",
    body: "Upload a class schedule or event flyer. Review every title, date, and time before the proposal reaches Google Calendar.",
    example: "Upload → review → apply",
  },
  {
    icon: Mic2,
    eyebrow: "Voice to calendar",
    title: "Capture plans before you forget them.",
    body: "Record a quick voice note. The transcript lands in the composer so you can edit the request before AI begins planning.",
    example: "“Move gym after the lab on Wednesday.”",
  },
];

export default function HomePage() {
  return (
    <main>
      <SiteHeader />
      <section className="hero">
        <div className="shell hero-grid">
          <div className="hero-copy">
            <div className="eyebrow"><Sparkles size={15} /> AI planning for ambitious weeks</div>
            <h1>Make space for what matters—<span>without burning out.</span></h1>
            <p className="hero-lede">
              Replanme turns deadlines, timetables, and voice notes into a realistic plan in Google Calendar—built around your energy, not just empty slots.
            </p>
            <div className="hero-actions">
              <Link className="button primary" href="/login">Plan my week <ArrowRight size={17} /></Link>
              <Link className="button secondary" href="/demo">Explore the demo</Link>
            </div>
            <div className="hero-proof">
              <span><CheckCircle2 size={16} /> Every change needs approval</span>
              <span><CheckCircle2 size={16} /> Built for Google Calendar</span>
            </div>
          </div>
          <WeekPreview />
        </div>
      </section>

      <section className="trust-strip" aria-label="Product principles">
        <div className="shell trust-grid">
          <div><Clock3 size={19} /><span><strong>Minutes, not hours</strong> from messy input to a clear week</span></div>
          <div><RefreshCw size={19} /><span><strong>Plan, approve, undo</strong> with an auditable workflow</span></div>
          <div><ShieldCheck size={19} /><span><strong>Private by design</strong> with short-lived AI context</span></div>
        </div>
      </section>

      <section className="section shell" id="workflows">
        <div className="section-heading">
          <p className="kicker">Three ways in. One calm plan out.</p>
          <h2>Your week can start as a sentence, a photo, or a voice note.</h2>
        </div>
        <div className="workflow-grid">
          {workflows.map(({ icon: Icon, ...item }, index) => (
            <article className="workflow-card" key={item.eyebrow}>
              <div className="card-index">0{index + 1}</div>
              <div className="feature-icon"><Icon size={21} /></div>
              <p className="card-eyebrow">{item.eyebrow}</p>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
              <div className="example-chip">{item.example}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="section shell">
        <div className="energy-section">
          <div>
            <p className="kicker">Energy-aware scheduling</p>
            <h2>Your best hour is more useful than your next empty hour.</h2>
            <p>
              Replanme keeps demanding work near your high-energy windows, respects fixed commitments, and protects recovery time when a week is already full.
            </p>
            <ul className="check-list">
              <li><CheckCircle2 size={18} /> Focus work matched to your energy profile</li>
              <li><CheckCircle2 size={18} /> Conflicts and overload surfaced before approval</li>
              <li><CheckCircle2 size={18} /> Plans stay editable—AI never gets the final word</li>
            </ul>
          </div>
          <div className="energy-card" aria-label="Daily energy profile">
            <div className="energy-card-head"><span>Wednesday capacity</span><span>Balanced</span></div>
            <div className="energy-chart">
              {[30, 46, 75, 92, 86, 60, 48, 67, 53, 31].map((height, index) => (
                <span key={index} style={{ height: `${height}%` }} />
              ))}
            </div>
            <div className="energy-labels"><span>8 AM</span><span>1 PM</span><span>6 PM</span></div>
            <div className="focus-match"><Sparkles size={16} /><span><strong>Best match:</strong> Portfolio deep work, 10:30–12:00</span></div>
          </div>
        </div>
      </section>

      <section className="section shell" id="security">
        <div className="security-panel">
          <div className="security-icon"><LockKeyhole size={28} /></div>
          <div>
            <p className="kicker">Designed for trust</p>
            <h2>Your calendar stays yours.</h2>
            <p>Google tokens are encrypted, uploads are processed in memory, and AI proposals expire. Every create, update, or delete waits for your explicit approval.</p>
          </div>
          <div className="security-list">
            <span><ShieldCheck size={18} /> Secure, HTTP-only sessions</span>
            <span><ShieldCheck size={18} /> No uploaded files stored</span>
            <span><ShieldCheck size={18} /> Review before calendar writes</span>
          </div>
        </div>
      </section>

      <section className="final-cta">
        <div className="shell">
          <p className="kicker">Your week, with breathing room.</p>
          <h2>Stop rearranging the same impossible plan.</h2>
          <p>Build a schedule that accounts for deadlines, energy, and the rest of your life.</p>
          <div className="hero-actions centered">
            <Link className="button primary light" href="/login">Continue with Google <ArrowRight size={17} /></Link>
            <Link className="button ghost" href="/demo">See a student week</Link>
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="shell footer-inner">
          <span>replanme</span>
          <p>An open-source AI calendar portfolio project.</p>
          <a href="https://github.com/avervill/replanme" target="_blank" rel="noreferrer">View on GitHub</a>
        </div>
      </footer>
    </main>
  );
}
