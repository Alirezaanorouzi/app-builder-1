import type { RefObject } from "react";
import { fa } from "@/lib/dict";
import { runEventTooltip } from "@/lib/run-events";

type RunEvent = {
  seq: number;
  event_class: string;
  tool_name: string | null;
  summary: string;
  payload?: Record<string, unknown>;
};

type Props = {
  events: RunEvent[];
  open: boolean;
  onToggle: () => void;
  endRef: RefObject<HTMLDivElement>;
};

export function ActivityRail({ events, open, onToggle, endRef }: Props) {
  const chips = events.slice(-14);

  return (
    <div className="activity-panel">
      <button
        type="button"
        className="activity-toggle"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span>{fa.activity}</span>
        <span className="activity-count">{events.length}</span>
        <span className="activity-toggle-label">
          {open ? fa.activityHide : fa.activityShow}
        </span>
      </button>
      {open ? (
        <div className="activity-strip" aria-live="polite">
          {chips.map((e) => (
            <span
              key={e.seq}
              className="activity-chip"
              title={runEventTooltip(e) ?? e.event_class}
            >
              {e.summary}
            </span>
          ))}
          <div ref={endRef} className="activity-strip-anchor" />
        </div>
      ) : (
        <div className="activity-strip activity-strip-collapsed">
          {chips.slice(-1).map((e) => (
            <span
              key={e.seq}
              className="activity-chip activity-chip-latest"
              title={runEventTooltip(e) ?? e.event_class}
            >
              {e.summary}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}