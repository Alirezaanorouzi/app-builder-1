export type RunEventRow = {
  seq: number;
  event_class: string;
  tool_name: string | null;
  payload?: Record<string, unknown>;
};

/** Short Farsi-friendly line for the activity feed (not a full event dump). */
export function summarizeRunEvent(row: RunEventRow): string {
  const tool = row.tool_name;
  if (tool) return `ابزار: ${tool}`;

  const cls = row.event_class;
  if (cls === "MessageEvent") {
    const src = row.payload?.source;
    if (src === "user") return "پیام کاربر";
    if (src === "agent") return "پاسخ agent";
    return "پیام";
  }
  if (cls.endsWith("Action")) return `اقدام · ${cls.replace(/Action$/, "")}`;
  if (cls.endsWith("Observation")) return `نتیجه · ${cls.replace(/Observation$/, "")}`;
  if (cls === "ConversationErrorEvent") {
    const code = row.payload?.code;
    return typeof code === "string" ? `خطا: ${code}` : "خطا در اجرا";
  }
  return cls;
}