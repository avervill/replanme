import { CalendarDays, Check, Sparkles } from "lucide-react";

const days = ["MON 12", "TUE 13", "WED 14", "THU 15", "FRI 16"];
const events = [
  { day: 0, top: 15, height: 28, title: "CS lecture", tone: "blue" },
  { day: 0, top: 51, height: 43, title: "Focus: algorithms", tone: "teal" },
  { day: 1, top: 28, height: 28, title: "Design critique", tone: "violet" },
  { day: 1, top: 66, height: 25, title: "Gym", tone: "sand" },
  { day: 2, top: 9, height: 54, title: "Internship", tone: "blue" },
  { day: 2, top: 70, height: 22, title: "Recovery walk", tone: "green" },
  { day: 3, top: 20, height: 35, title: "Deep work", tone: "teal" },
  { day: 3, top: 62, height: 30, title: "Statistics", tone: "violet" },
  { day: 4, top: 12, height: 38, title: "Portfolio ship", tone: "blue" },
  { day: 4, top: 60, height: 22, title: "Free evening", tone: "green" },
];

export function WeekPreview() {
  return (
    <div className="product-preview" aria-label="AI calendar planning preview">
      <div className="preview-topbar">
        <div className="preview-title"><CalendarDays size={16} /> May 12–16</div>
        <span className="status-pill"><span /> Calendar connected</span>
      </div>
      <div className="preview-body">
        <div className="week-grid">
          {days.map((day, index) => (
            <div className="preview-day" key={day}>
              <span>{day}</span>
              <div className="day-track">
                {events.filter((event) => event.day === index).map((event) => (
                  <div
                    key={event.title}
                    className={`preview-event ${event.tone}`}
                    style={{ top: `${event.top}%`, height: `${event.height}%` }}
                  >
                    {event.title}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="preview-assistant">
          <div className="assistant-label"><Sparkles size={15} /> Planning proposal</div>
          <p>I found two calm windows before your Friday deadline.</p>
          <div className="proposal-row"><Check size={14} /> Add 2 focus sessions</div>
          <div className="proposal-row"><Check size={14} /> Keep Thursday evening free</div>
          <button type="button">Apply 2 changes</button>
        </div>
      </div>
    </div>
  );
}
