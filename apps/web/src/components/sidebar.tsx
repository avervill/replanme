import Link from "next/link";

interface SidebarSection {
  icon: string;
  label: string;
  href: string;
  active?: boolean;
}

export function Sidebar() {
  const sections: SidebarSection[] = [
    { icon: "📅", label: "Today", href: "#today", active: false },
    { icon: "📆", label: "This Week", href: "#week", active: true },
    { icon: "🎯", label: "Goals", href: "#goals", active: false },
    { icon: "⚙️", label: "Settings", href: "#settings", active: false },
  ];

  return (
    <aside className="hidden flex-col border-r border-calm-primary/10 lg:flex">
      <div className="space-y-1 p-4">
        <h2 className="px-2 text-xs font-semibold uppercase tracking-widest text-calm-muted">
          Navigation
        </h2>
        <nav className="space-y-1">
          {sections.map((section) => (
            <a
              key={section.label}
              href={section.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                section.active
                  ? "bg-calm-primary/20 text-calm-primary"
                  : "text-calm-muted hover:text-calm-text hover:bg-calm-card"
              }`}
            >
              <span className="text-base">{section.icon}</span>
              <span>{section.label}</span>
            </a>
          ))}
        </nav>
      </div>

      <div className="mt-auto space-y-4 border-t border-calm-primary/10 p-4">
        <div className="rounded-lg bg-calm-primary/10 p-3 text-xs">
          <p className="font-semibold text-calm-primary">Pro Tip</p>
          <p className="mt-2 text-calm-muted">
            Ask the AI to "fix conflicts" if your schedule has overlaps.
          </p>
        </div>

        <div className="text-xs text-calm-muted">
          <p>📧 Feedback?</p>
          <a href="#" className="mt-2 inline-block text-calm-primary hover:underline">
            Send us a message
          </a>
        </div>
      </div>
    </aside>
  );
}
