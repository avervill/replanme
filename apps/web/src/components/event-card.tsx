import React from "react";

interface EventCardProps {
  id: string;
  title: string;
  startTime: string;
  endTime: string;
  type?: "work" | "personal" | "study" | "default";
  isConflict?: boolean;
  onEdit?: (id: string) => void;
  onDelete?: (id: string) => void;
  onMove?: (id: string) => void;
  onResolveConflict?: (id: string) => void;
  onIgnoreConflict?: (id: string) => void;
  className?: string;
}

const typeIcons: Record<string, React.ReactNode> = {
  work: <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="20" height="14" x="2" y="7" rx="2" ry="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" /></svg>,
  personal: <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></svg>,
  study: <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" /></svg>,
  default: <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2" /><line x1="16" x2="16" y1="2" y2="6" /><line x1="8" x2="8" y1="2" y2="6" /><line x1="3" x2="21" y1="10" y2="10" /></svg>,
};

const typeColors: Record<string, { bg: string; border: string; icon: string }> = {
  work: { bg: "bg-[#e0f2fe]", border: "border-[#0284c7]", icon: "text-[#0369a1]" },
  personal: { bg: "bg-[#dcfce7]", border: "border-[#16a34a]", icon: "text-[#15803d]" },
  study: { bg: "bg-[#f3e8ff]", border: "border-[#9333ea]", icon: "text-[#7e22ce]" },
  default: { bg: "bg-[#fef3c7]", border: "border-[#d97706]", icon: "text-[#b45309]" },
};

export function EventCard({
  id,
  title,
  startTime,
  endTime,
  type = "default",
  isConflict = false,
  onResolveConflict,
  onIgnoreConflict,
  className = "",
}: EventCardProps) {
  const colors = typeColors[type] || typeColors.default;
  const icon = typeIcons[type] || typeIcons.default;

  const conflictClasses = isConflict
    ? "border-[2px] border-red-500/50 bg-red-500/10 shadow-[0_0_15px_rgba(239,68,68,0.3)] animate-pulse-soft"
    : `border ${colors.border} border-l-[4px] ${colors.bg}`;

  return (
    <div
      data-event-type={isConflict ? "conflict" : type}
      className={`group relative rounded-[12px] p-3 transition-all duration-200 overflow-hidden shadow-calm-sm hover:shadow-calm-md hover:scale-[1.02] ${conflictClasses} ${className} flex items-start`}
    >
      <div className={`mt-0.5 shrink-0 ${colors.icon}`}>{icon}</div>
      <div className="flex-1 min-w-0 ml-3 flex flex-col justify-between h-full relative z-10 w-full pr-0">
        <div>
          <h4 className="font-semibold text-white whitespace-normal break-words text-[13px] leading-tight">{title}</h4>
          <div className="h-1" />
          <p className="text-[11px] text-calm-muted uppercase tracking-wider font-medium whitespace-normal break-words">
            {startTime} <span className="opacity-50 mx-1">&bull;</span> {endTime}
          </p>
        </div>

        {isConflict && (
          <div className="mt-2 flex flex-col gap-1 items-start">
            <div className="inline-block bg-red-500/20 text-red-300 text-[10px] rounded px-1.5 py-0.5 font-bold uppercase tracking-wider">
              ⚠️ Conflict
            </div>
            {(onResolveConflict || onIgnoreConflict) && (
              <div className="flex gap-1 mt-1">
                {onResolveConflict && (
                  <button onClick={(e) => { e.stopPropagation(); onResolveConflict(id); }} className="text-[10px] bg-red-500/80 text-white px-2 py-0.5 rounded font-medium hover:bg-red-500 transition-colors pointer-events-auto">Fix</button>
                )}
                {onIgnoreConflict && (
                  <button onClick={(e) => { e.stopPropagation(); onIgnoreConflict(id); }} className="text-[10px] border border-red-500/30 text-red-300 px-2 py-0.5 rounded font-medium hover:bg-red-500/10 transition-colors pointer-events-auto">Ignore</button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function EventCardSkeleton() {
  return (
    <div className="rounded-[12px] p-3 border-l-[3px] border-[rgba(255,255,255,0.1)] bg-[rgba(255,255,255,0.03)] animate-pulse flex items-start">
      <div className="w-4 h-4 rounded-sm bg-white/10"></div>
      <div className="flex-1 space-y-2 ml-3 mt-1 cursor-default">
        <div className="h-2.5 bg-white/10 rounded w-2/3"></div>
        <div className="h-2 bg-white/5 rounded w-1/3"></div>
      </div>
    </div>
  );
}
