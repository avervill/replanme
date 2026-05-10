import React, { useState } from "react";

interface ConflictResolverProps {
  conflictEvents: Array<{
    id: string;
    title: string;
    startTime: string;
    endTime: string;
  }>;
  suggestedResolution?: {
    eventId: string;
    newStartTime: string;
    newEndTime: string;
    reason: string;
  };
  onResolve: (eventId: string, newStart: string, newEnd: string) => void;
  onIgnore: (eventIds: string[]) => void;
}

export function ConflictResolver({
  conflictEvents,
  suggestedResolution,
  onResolve,
  onIgnore,
}: ConflictResolverProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div className="calm-card border-red-500/50 bg-red-500/5 space-y-4">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="text-2xl">⚠️</div>
        <div className="flex-1">
          <h3 className="font-bold text-calm-text">Schedule Conflict Detected</h3>
          <p className="text-sm text-calm-muted mt-1">
            {conflictEvents.length} events overlap. We can help you fix this.
          </p>
        </div>
      </div>

      {/* Conflicting Events */}
      <div className="space-y-2">
        {conflictEvents.map((event) => (
          <div key={event.id} className="p-2 rounded bg-calm-card/50 border border-calm-primary/10">
            <p className="font-semibold text-sm text-calm-text">{event.title}</p>
            <p className="text-xs text-calm-muted">{event.startTime} – {event.endTime}</p>
          </div>
        ))}
      </div>

      {/* Suggested Resolution */}
      {suggestedResolution && (
        <div className="p-3 rounded-lg bg-calm-secondary/10 border border-calm-secondary/30 space-y-2">
          <p className="text-xs font-semibold text-calm-secondary">💡 AI Suggestion</p>
          <p className="text-sm text-calm-text">
            Move <strong>{suggestedResolution.eventId}</strong> to{" "}
            <strong>{suggestedResolution.newStartTime}</strong>
          </p>
          <p className="text-xs text-calm-muted italic">{suggestedResolution.reason}</p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => {
            if (suggestedResolution) {
              onResolve(
                suggestedResolution.eventId,
                suggestedResolution.newStartTime,
                suggestedResolution.newEndTime
              );
            }
            setDismissed(true);
          }}
          className="btn-primary flex-1 text-sm"
        >
          Apply Fix
        </button>
        <button
          onClick={() => {
            onIgnore(conflictEvents.map((e) => e.id));
            setDismissed(true);
          }}
          className="btn-secondary flex-1 text-sm"
        >
          Ignore
        </button>
      </div>

      <p className="text-xs text-calm-muted">
        We won't show this conflict again if you ignore it.
      </p>
    </div>
  );
}
