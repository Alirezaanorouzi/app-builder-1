import { useEffect, useRef } from "react";
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
};

/** One live line. The latest step replaces the previous one. The arrow opens the full list. */
export function ActivityRail({ events, open, onToggle }: Props) {
  const latest = events[events.length - 1];
  const listRef = useRef<HTMLOListElement | null>(null);
  useEffect(() => {
    if (!open) return;
    listRef.current?.lastElementChild?.scrollIntoView({ block: "nearest" });
  }, [open, events.length]);
  if (!latest) return null;

  return (
    <div className="live-activity">
      <button
        type="button"
        className="live-activity-line"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className="live-activity-mark" aria-hidden />
        <span className="live-activity-text" title={runEventTooltip(latest) ?? latest.summary}>
          {latest.summary}
        </span>
        <svg
          className={`live-activity-chevron${open ? " live-activity-chevron-open" : ""}`}
          width="16"
          height="16"
          viewBox="0 0 24 24"
          aria-hidden
        >
          <path fill="currentColor" d="M7.4 8.6 12 13.2l4.6-4.6L18 10l-6 6-6-6z" />
        </svg>
      </button>
      {open ? (
        <ol ref={listRef} className="live-activity-list">
          {events.map((event) => (
            <li
              key={event.seq}
              className={
                event.seq === latest.seq
                  ? "live-activity-item live-activity-item-current"
                  : "live-activity-item"
              }
              title={runEventTooltip(event) ?? event.summary}
            >
              {event.summary}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
