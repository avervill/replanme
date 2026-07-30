"use client";

import Link from "next/link";
import {
  ArrowRight,
  CalendarDays,
  Camera,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Mic2,
  PanelRightClose,
  PanelRightOpen,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Brand } from "@/components/brand";
import {
  applyCalendarPlan,
  importScheduleImage,
  streamAssistantMessage,
  transcribeVoice,
  updateCalendarPlan,
  type CalendarChangePlan,
} from "@/lib/api";

export type CalendarExperienceMode = "demo" | "dashboard";

type WeekEvent = {
  id: string;
  day: number;
  start: number;
  duration: number;
  title: string;
  detail: string;
  tone: "blue" | "teal" | "violet" | "sand" | "green";
};

const baseEvents: WeekEvent[] = [
  { id: "cs", day: 0, start: 1, duration: 1, title: "CS 301 · Algorithms", detail: "9:00–10:00 · Hall B", tone: "blue" },
  { id: "deep-1", day: 0, start: 3, duration: 2, title: "Algorithms problem set", detail: "11:00–1:00 · Focus", tone: "teal" },
  { id: "research", day: 0, start: 7, duration: 1, title: "Research sync", detail: "3:00–4:00 · Zoom", tone: "violet" },
  { id: "design", day: 1, start: 2, duration: 1.5, title: "Design systems", detail: "10:00–11:30 · Studio 4", tone: "violet" },
  { id: "deadline", day: 1, start: 5, duration: 1, title: "Submit fellowship draft", detail: "1:00–2:00 · Deadline", tone: "sand" },
  { id: "gym", day: 1, start: 8, duration: 1, title: "Strength training", detail: "4:00–5:00 · Gym", tone: "green" },
  { id: "intern", day: 2, start: 1, duration: 4, title: "Product internship", detail: "9:00–1:00 · Remote", tone: "blue" },
  { id: "stats", day: 2, start: 6, duration: 1.5, title: "Statistics seminar", detail: "2:00–3:30 · Room 210", tone: "violet" },
  { id: "walk", day: 2, start: 9, duration: 1, title: "Recovery walk", detail: "5:00–6:00", tone: "green" },
  { id: "portfolio", day: 3, start: 2, duration: 2, title: "Portfolio deep work", detail: "10:00–12:00 · Focus", tone: "teal" },
  { id: "mentor", day: 3, start: 6, duration: 1, title: "Mentor office hours", detail: "2:00–3:00", tone: "blue" },
  { id: "quiet", day: 3, start: 9, duration: 1.5, title: "Low-energy evening", detail: "Protected recovery", tone: "green" },
  { id: "ship", day: 4, start: 1.5, duration: 2, title: "Ship portfolio case study", detail: "9:30–11:30 · Deadline", tone: "sand" },
  { id: "intern-2", day: 4, start: 5, duration: 3, title: "Product internship", detail: "1:00–4:00 · Remote", tone: "blue" },
];

const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
const shortDays = ["MON", "TUE", "WED", "THU", "FRI"];
const timeLabels = ["8 AM", "9 AM", "10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "6 PM"];

export function CalendarExperience({ mode }: { mode: CalendarExperienceMode }) {
  const [weekOffset, setWeekOffset] = useState(0);
  const [gateOpen, setGateOpen] = useState(false);
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [composer, setComposer] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [applied, setApplied] = useState(false);
  const [importReview, setImportReview] = useState(false);
  const [importedTitles, setImportedTitles] = useState(["Product strategy workshop", "Career fair"]);
  const [proposedPlan, setProposedPlan] = useState<CalendarChangePlan | null>(null);
  const [assistantText, setAssistantText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const weekLabel = useMemo(() => {
    if (weekOffset === 0) return "May 12–16, 2026";
    const start = 12 + weekOffset * 7;
    return `May ${start}–${start + 4}, 2026`;
  }, [weekOffset]);

  const mutate = () => {
    if (mode === "demo") setGateOpen(true);
  };

  const sendPrompt = async () => {
    if (mode === "demo") {
      setGateOpen(true);
      return;
    }
    if (!composer.trim() || busy) return;
    setBusy(true);
    setError("");
    setAssistantText("");
    try {
      await streamAssistantMessage(composer, "UTC", (event, payload) => {
        if (event === "delta") setAssistantText(String(payload.text ?? ""));
        if (event === "plan") {
          setProposedPlan(payload as unknown as CalendarChangePlan);
          setSubmitted(true);
        }
        if (event === "error") setError(String(payload.message ?? "Planning failed"));
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Planning failed");
    } finally {
      setBusy(false);
    }
  };

  const openImageImport = () => {
    if (mode === "demo") {
      setGateOpen(true);
      return;
    }
    document.getElementById("schedule-image-input")?.click();
  };

  return (
    <div className="app-page">
      <header className="app-header">
        <div className="app-header-inner">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Brand compact />
            {mode === "demo" && <span className="demo-badge">Read-only demo</span>}
          </div>
          <div className="app-header-actions">
            {mode === "demo" ? (
              <>
                <Link className="toolbar-button hide-mobile" href="/">Back to site</Link>
                <Link className="button primary" style={{ minHeight: 38, padding: "0 14px" }} href="/login">
                  Try with my calendar
                </Link>
              </>
            ) : (
              <button className="toolbar-button" type="button">Jamie <ChevronDown size={13} /></button>
            )}
          </div>
        </div>
      </header>
      <div className="app-layout" style={panelCollapsed ? { gridTemplateColumns: "1fr 64px" } : undefined}>
        <section className="calendar-area" aria-label="Calendar">
          <div className="calendar-toolbar">
            <div className="calendar-nav">
              <button className="toolbar-button icon-only" onClick={() => setWeekOffset((value) => value - 1)} aria-label="Previous week"><ChevronLeft size={16} /></button>
              <button className="toolbar-button icon-only" onClick={() => setWeekOffset((value) => value + 1)} aria-label="Next week"><ChevronRight size={16} /></button>
              <h1>{weekLabel}</h1>
              {weekOffset !== 0 && <button className="toolbar-button" onClick={() => setWeekOffset(0)}>Today</button>}
            </div>
            <div className="toolbar-right">
              <button className="toolbar-button hide-mobile" onClick={mutate}><CalendarDays size={14} /> New event</button>
              <button className="toolbar-button">Week <ChevronDown size={13} /></button>
            </div>
          </div>
          <div className="calendar-shell">
            <div className="calendar-week">
              <div className="time-column">
                {timeLabels.map((time) => <span key={time}>{time}</span>)}
              </div>
              {dayNames.map((day, dayIndex) => (
                <div className="calendar-column" key={day}>
                  <div className="day-heading">{shortDays[dayIndex]}<strong>{12 + dayIndex + weekOffset * 7}</strong></div>
                  {weekOffset === 0 && baseEvents.filter((event) => event.day === dayIndex).map((event) => (
                    <button
                      type="button"
                      key={event.id}
                      onClick={mutate}
                      className={`cal-event ${event.tone}`}
                      style={{ top: 51 + event.start * 55, height: Math.max(39, event.duration * 55 - 4) }}
                    >
                      <strong>{event.title}</strong><span>{event.detail}</span>
                    </button>
                  ))}
                  {applied && weekOffset === 0 && dayIndex === 1 && (
                    <button type="button" onClick={mutate} className="cal-event teal" style={{ top: 51 + 3.5 * 55, height: 78 }}>
                      <strong>Statistics review</strong><span>11:30–1:00 · Focus</span>
                    </button>
                  )}
                </div>
              ))}
            </div>
            <div className="mobile-agenda">
              {dayNames.map((day, dayIndex) => (
                <section className="agenda-day" key={day}>
                  <h2>{day}, May {12 + dayIndex + weekOffset * 7}</h2>
                  {weekOffset === 0 ? baseEvents.filter((event) => event.day === dayIndex).map((event) => (
                    <button className="agenda-item" type="button" key={event.id} onClick={mutate} style={{ width: "100%", textAlign: "left" }}>
                      <span className="agenda-time">{event.detail.split(" · ")[0]}</span>
                      <span><strong>{event.title}</strong><p>{event.detail.split(" · ")[1] ?? "Calendar event"}</p></span>
                    </button>
                  )) : <p style={{ color: "#718096", fontSize: 12 }}>No demo events this week.</p>}
                </section>
              ))}
            </div>
          </div>
        </section>
        <aside className={panelCollapsed ? "ai-panel is-collapsed" : "ai-panel"} aria-label="AI planning assistant">
          <div className="ai-panel-head">
            {!panelCollapsed && <div className="ai-title"><Sparkles size={16} /> AI planner</div>}
            <button className="icon-button" onClick={() => setPanelCollapsed((value) => !value)} aria-label={panelCollapsed ? "Open AI panel" : "Collapse AI panel"}>
              {panelCollapsed ? <PanelRightOpen size={17} /> : <PanelRightClose size={17} />}
            </button>
          </div>
          <div className="ai-thread">
            <div className="ai-intro">
              <Sparkles size={20} />
              <h2>Plan around real capacity</h2>
              <p>Ask for a focused, conflict-aware proposal. Nothing changes until you approve it.</p>
            </div>
            {!submitted && (
              <div className="suggestion-list">
                {["Fit in study time before Friday", "Protect two recovery evenings", "Reschedule work around my internship"].map((text) => (
                  <button className="suggestion" key={text} onClick={() => { setComposer(text); if (mode === "demo") setGateOpen(true); }}>{text}</button>
                ))}
              </div>
            )}
            {submitted && (
              <>
                <div className="chat-bubble user">{composer}</div>
                <div className="chat-bubble assistant">
                  {assistantText || proposedPlan?.summary || "I found a 90-minute high-energy window on Tuesday and kept your recovery blocks intact."}
                  <div className="plan-card">
                    <h3>Proposed calendar change</h3>
                    {(proposedPlan?.changes.length ? proposedPlan.changes : [{ type: "create", title: "Statistics review" }]).slice(0, 4).map((change, index) => (
                      <div className="plan-item" key={`${change.type}-${index}`}>
                        <Sparkles size={14} /> {change.type} “{change.title ?? ("event_id" in change ? change.event_id : undefined) ?? "calendar event"}”
                      </div>
                    ))}
                    <div className="plan-item"><ShieldMini /> No conflicts detected</div>
                    <div className="plan-actions">
                      <button className="button secondary" onClick={() => setSubmitted(false)}>Keep editing</button>
                      <button className="button primary" disabled={busy} onClick={async () => {
                        if (!proposedPlan) {
                          setApplied(true);
                          return;
                        }
                        setBusy(true);
                        try {
                          const result = await applyCalendarPlan(proposedPlan.id);
                          setProposedPlan(result.plan);
                          setApplied(true);
                        } catch (requestError) {
                          setError(requestError instanceof Error ? requestError.message : "Could not apply plan");
                        } finally {
                          setBusy(false);
                        }
                      }}>{applied ? "Applied" : busy ? "Working…" : "Apply change"}</button>
                    </div>
                  </div>
                </div>
              </>
            )}
            {error && <div className="chat-bubble assistant" role="alert">{error}</div>}
          </div>
          <div className="ai-composer">
            <div className="composer-box">
              <textarea value={composer} onChange={(event) => setComposer(event.target.value)} placeholder="What should this week make room for?" aria-label="Message AI planner" />
              <div className="composer-actions">
                <div className="composer-tools">
                  <button type="button" aria-label="Import schedule photo" title="Import schedule photo" onClick={openImageImport}><Camera size={15} /></button>
                  <button type="button" aria-label="Add recorded voice note" title="Add recorded voice note" onClick={() => mode === "demo" ? setGateOpen(true) : document.getElementById("voice-recording-input")?.click()}><Mic2 size={15} /></button>
                </div>
                <button type="button" className="send-button" aria-label="Send message" onClick={() => void sendPrompt()} disabled={busy}><Send size={15} /></button>
              </div>
            </div>
          </div>
          <input
            id="schedule-image-input"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            hidden
            onChange={(event) => {
              const selected = event.target.files?.[0];
              if (!selected) return;
              setBusy(true);
              setError("");
              void importScheduleImage(selected)
                .then((plan) => {
                  setProposedPlan(plan);
                  const titles = plan.changes.filter((change) => change.type === "create").map((change) => change.title ?? "Untitled event");
                  setImportedTitles(titles.length ? titles : ["Untitled event"]);
                  setImportReview(true);
                })
                .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Image import failed"))
                .finally(() => setBusy(false));
            }}
          />
          <input
            id="voice-recording-input"
            type="file"
            accept="audio/webm,audio/mp4,audio/mpeg,audio/wav,audio/ogg"
            hidden
            onChange={(event) => {
              const selected = event.target.files?.[0];
              if (!selected) return;
              setBusy(true);
              setError("");
              void transcribeVoice(selected)
                .then((result) => setComposer(result.transcript))
                .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Transcription failed"))
                .finally(() => setBusy(false));
            }}
          />
        </aside>
      </div>
      {gateOpen && (
        <div className="gating-overlay" role="dialog" aria-modal="true" aria-labelledby="gate-title">
          <div className="gating-card">
            <button className="icon-button" style={{ position: "absolute", transform: "translate(330px,-15px)" }} onClick={() => setGateOpen(false)} aria-label="Close sign-in prompt"><X size={17} /></button>
            <div className="feature-icon"><Sparkles size={21} /></div>
            <h2 id="gate-title">Ready to plan your own week?</h2>
            <p>The demo is safely read-only. Connect Google Calendar to ask AI, import a timetable, or edit an event.</p>
            <div className="gating-actions">
              <button className="button secondary" onClick={() => setGateOpen(false)}>Keep exploring</button>
              <Link className="button primary" href="/login">Continue with Google <ArrowRight size={15} /></Link>
            </div>
          </div>
        </div>
      )}
      {importReview && (
        <div className="gating-overlay" role="dialog" aria-modal="true" aria-labelledby="review-title">
          <div className="gating-card" style={{ textAlign: "left", width: "min(540px, 100%)" }}>
            <div className="feature-icon"><Camera size={21} /></div>
            <h2 id="review-title">Review extracted events</h2>
            <p>Check every title and time before creating a calendar proposal.</p>
            <div style={{ display: "grid", gap: 10, marginTop: 18 }}>
              {importedTitles.map((title, index) => (
                <label key={index} style={{ display: "grid", gap: 6, color: "#52647b", fontSize: 11 }}>
                  Event {index + 1}
                  <input
                    value={title}
                    onChange={(event) => setImportedTitles((current) => current.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}
                    style={{ minHeight: 42, padding: "0 11px", border: "1px solid #cfd9e6", borderRadius: 8, color: "#12233d" }}
                  />
                  <span>{index === 0 ? "Wed, May 14 · 11:00 AM–12:00 PM" : "Thu, May 15 · 3:00–5:00 PM"}</span>
                </label>
              ))}
            </div>
            <div className="gating-actions" style={{ justifyContent: "flex-end" }}>
              <button className="button secondary" onClick={() => setImportReview(false)}>Cancel</button>
              <button className="button primary" onClick={() => {
                if (!proposedPlan) return;
                const editedPlan = {
                  ...proposedPlan,
                  changes: proposedPlan.changes.map((change, index) => (
                    change.type === "create" ? { ...change, title: importedTitles[index] ?? change.title } : change
                  )),
                };
                setBusy(true);
                void updateCalendarPlan(editedPlan)
                  .then((plan) => {
                    setProposedPlan(plan);
                    setAssistantText(`I extracted ${plan.changes.length} event(s). Review the proposal once more before applying.`);
                    setComposer(`Import ${plan.changes.length} reviewed events from my schedule photo.`);
                    setImportReview(false);
                    setSubmitted(true);
                  })
                  .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Could not save edits"))
                  .finally(() => setBusy(false));
              }}>Create proposal</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ShieldMini() {
  return (
    <span aria-hidden="true" style={{ width: 14, height: 14, borderRadius: 7, background: "#0f9f94", color: "white", display: "inline-grid", placeItems: "center", fontSize: 8 }}>✓</span>
  );
}
