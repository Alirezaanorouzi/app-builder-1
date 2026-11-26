export type RunEventRow = {
  seq: number;
  event_class: string;
  tool_name: string | null;
  payload?: Record<string, unknown>;
};

const INTERNAL_RUN_EVENTS = new Set([
  "RunTimelineEvent",
  "StreamingDeltaEvent",
  "ConversationStateUpdateEvent",
]);

/** Steps worth showing on the live activity line. Token and stats events stay off it. */
export function isActivityChipEvent(
  row: Pick<RunEventRow, "event_class">,
): boolean {
  return !INTERNAL_RUN_EVENTS.has(row.event_class);
}

const CHIP_MAX_LEN = 80;
const PERSIAN_RE = /[\u0600-\u06FF]/;

function hasPersian(text: string): boolean {
  return PERSIAN_RE.test(text);
}

function clip(text: string, max = CHIP_MAX_LEN): string {
  const t = text.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function basenameFromPayload(payload?: Record<string, unknown>): string | null {
  const action = payload?.action as Record<string, unknown> | undefined;
  const path =
    (action?.path as string) ||
    (payload?.path as string) ||
    (action?.command as string);
  if (typeof path !== "string" || !path) return null;
  const parts = path.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path;
}

function sdkSummary(payload?: Record<string, unknown>): string | null {
  const raw = payload?.summary;
  if (typeof raw !== "string") return null;
  const s = raw.trim();
  return s || null;
}

/** SDK default when the model omits summary: `tool_name: {"..."}`. */
function isSdkFallbackSummary(summary: string, tool: string | null): boolean {
  if (!tool) return false;
  if (!summary.startsWith(`${tool}:`)) return false;
  return summary.includes("{") || summary.includes("\\");
}

function thoughtTexts(payload?: Record<string, unknown>): string[] {
  const thought = payload?.thought;
  if (!Array.isArray(thought)) return [];
  return thought
    .map((item) => {
      if (item && typeof item === "object" && "text" in item) {
        return String((item as { text: string }).text).trim();
      }
      return "";
    })
    .filter(Boolean);
}

function firstSentence(text: string): string {
  const m = text.trim().match(/^[^.!?؟\n]+[.!?؟]?/u);
  return (m?.[0] ?? text).trim();
}

function persianClip(text: string | null | undefined): string | null {
  if (!text) return null;
  const trimmed = text.trim();
  if (!trimmed || !hasPersian(trimmed)) return null;
  return clip(trimmed);
}

function persianToolPhrase(tool: string | null, file: string | null): string {
  if (tool === "file_editor" && file) return clip(`ویرایش ${file}`);
  if (tool === "file_editor") return "ویرایش فایل";
  if (tool === "terminal") return "اجرای دستور";
  if (tool === "task_tracker") return "برنامه‌ریزی کارها";
  if (tool === "think") return "در حال فکر کردن";
  if (tool === "finish") return "جمع‌بندی کار";
  if (tool === "browser") return "بررسی صفحه";
  return "در حال انجام کار";
}

function actionEventLabel(row: RunEventRow): string {
  const payload = row.payload;
  const tool = row.tool_name;
  const fromSdk = sdkSummary(payload);
  const thoughts = thoughtTexts(payload);
  const thoughtLine = thoughts.length > 0 ? firstSentence(thoughts.join(" ")) : null;
  const rc = payload?.reasoning_content;
  const reasoningLine = typeof rc === "string" && rc.trim() ? firstSentence(rc) : null;

  const persian =
    (fromSdk && !isSdkFallbackSummary(fromSdk, tool) ? persianClip(fromSdk) : null) ??
    persianClip(thoughtLine) ??
    persianClip(reasoningLine);
  if (persian) return persian;

  return persianToolPhrase(tool, basenameFromPayload(payload));
}

/** Longer hint for chip hover (optional). */
export function runEventTooltip(row: RunEventRow): string | undefined {
  const payload = row.payload;
  const parts: string[] = [];
  const fromSdk = sdkSummary(payload);
  if (fromSdk) parts.push(fromSdk);
  const thoughts = thoughtTexts(payload);
  if (thoughts.length) parts.push(thoughts.join("\n"));
  const rc = payload?.reasoning_content;
  if (typeof rc === "string" && rc.trim()) parts.push(rc.trim());
  if (!parts.length) return undefined;
  const merged = parts.join("\n\n");
  return merged.length > 500 ? `${merged.slice(0, 497)}…` : merged;
}

/** Short label for horizontal activity chips. */
export function summarizeRunEvent(row: RunEventRow): string {
  const tool = row.tool_name;
  const cls = row.event_class;

  if (cls === "ActionEvent") {
    return actionEventLabel(row);
  }

  const file = basenameFromPayload(row.payload);
  if (tool === "file_editor" || tool === "terminal" || tool === "task_tracker") {
    return persianToolPhrase(tool, file);
  }
  if (tool) return persianToolPhrase(tool, file);

  if (cls === "RunBootstrapEvent") {
    const s = sdkSummary(row.payload);
    return persianClip(s) ?? "آماده‌سازی";
  }
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