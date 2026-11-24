import { isActivityChipEvent, type RunEventRow } from "@/lib/run-events";

export const THINKING_DELAY_MS = 1000;

/** Hide the thinking loader once agent output or a real run event appears. */
export function shouldHideThinkingLoader(
  events: Pick<RunEventRow, "event_class" | "tool_name">[],
  liveOutput: string | null,
): boolean {
  if (liveOutput?.trim()) return true;
  return events.some(
    (e) => isActivityChipEvent(e) && e.event_class !== "RunBootstrapEvent",
  );
}