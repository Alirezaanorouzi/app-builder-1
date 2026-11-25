import { query } from "@/lib/db";
import { summarizeRunEvent, type RunEventRow } from "@/lib/run-events";

export type ProjectStreamMessage = {
  id: string;
  role: string;
  content: string;
  created_at?: string;
  run_id?: string | null;
};

export type ProjectStreamActiveRun = {
  id: string;
  status: string;
  live_output: string | null;
} | undefined;

export type ProjectStreamRunEvent = {
  seq: number;
  event_class: string;
  tool_name: string | null;
  summary: string;
};

function toWireEvent(row: RunEventRow): ProjectStreamRunEvent {
  return {
    seq: row.seq,
    event_class: row.event_class,
    tool_name: row.tool_name,
    summary: summarizeRunEvent(row),
  };
}

/** True when a delta should be pushed. Avoids resending an unchanged full history. */
export function streamDeltaChanged(
  prev: ProjectStreamUpdate,
  delta: ProjectStreamUpdate,
): boolean {
  if (delta.messages.length > 0 || delta.runEvents.length > 0) return true;
  if ((delta.activeRun?.id ?? null) !== (prev.activeRun?.id ?? null)) return true;
  if ((delta.activeRun?.status ?? null) !== (prev.activeRun?.status ?? null)) return true;
  if ((delta.liveOutput ?? null) !== (prev.liveOutput ?? null)) return true;
  if ((delta.previewUrl ?? null) !== (prev.previewUrl ?? null)) return true;
  if ((delta.previewWake?.id ?? null) !== (prev.previewWake?.id ?? null)) return true;
  if ((delta.previewWake?.status ?? null) !== (prev.previewWake?.status ?? null)) return true;
  if ((delta.sandbox?.preview_url ?? null) !== (prev.sandbox?.preview_url ?? null)) return true;
  if ((delta.sandbox?.status ?? null) !== (prev.sandbox?.status ?? null)) return true;
  if ((delta.sandbox?.agent_server_status ?? null) !== (prev.sandbox?.agent_server_status ?? null))
    return true;
  if ((delta.sandbox?.session_expires_at ?? null) !== (prev.sandbox?.session_expires_at ?? null))
    return true;
  return false;
}

export type ProjectStreamSandbox = {
  preview_url: string | null;
  provider: string | null;
  external_id: string | null;
  status: string | null;
  name: string | null;
  agent_server_status: string | null;
  session_expires_at: string | null;
} | null;

export type ProjectStreamUpdate = {
  messages: ProjectStreamMessage[];
  activeRun: ProjectStreamActiveRun;
  liveOutput: string | null;
  previewUrl: string | null;
  runEvents: ProjectStreamRunEvent[];
  sandbox: ProjectStreamSandbox;
  previewWake: { id: string; status: string } | null;
};

export type ProjectStreamCursor = {
  lastMessageId: string | null;
  lastMessageAt: string | null;
  activeRunId: string | null;
  lastRunEventSeq: number;
};

const MESSAGE_CAP = 50;

export const PROJECT_STREAM_NOTIFY_CHANNEL = "builder_project_stream";

export function cursorFromSnapshot(update: ProjectStreamUpdate): ProjectStreamCursor {
  const lastMsg = update.messages[update.messages.length - 1];
  const lastEvent = update.runEvents[update.runEvents.length - 1];
  return {
    lastMessageId: lastMsg?.id ?? null,
    lastMessageAt: lastMsg?.created_at ?? null,
    activeRunId: update.activeRun?.id ?? null,
    lastRunEventSeq: lastEvent?.seq ?? -1,
  };
}

export function mergeProjectStreamUpdates(
  prev: ProjectStreamUpdate,
  delta: ProjectStreamUpdate,
): ProjectStreamUpdate {
  const runChanged =
    (delta.activeRun?.id ?? null) !== (prev.activeRun?.id ?? null) ||
    (delta.activeRun?.status ?? null) !== (prev.activeRun?.status ?? null);

  let messages = prev.messages;
  if (delta.messages.length) {
    const seen = new Set(prev.messages.map((m) => m.id));
    const appended = delta.messages.filter((m) => !seen.has(m.id));
    if (appended.length) {
      messages = [...prev.messages, ...appended].slice(-MESSAGE_CAP);
    }
  }

  let runEvents = prev.runEvents;
  if (runChanged && delta.runEvents.length) {
    runEvents = delta.runEvents;
  } else if (delta.runEvents.length) {
    const seenSeq = new Set(prev.runEvents.map((e) => e.seq));
    const appended = delta.runEvents.filter((e) => !seenSeq.has(e.seq));
    if (appended.length) {
      runEvents = [...prev.runEvents, ...appended];
    }
  }

  const liveOutput =
    delta.activeRun?.status === "running"
      ? delta.liveOutput ?? prev.liveOutput
      : delta.liveOutput;

  return {
    messages,
    activeRun: delta.activeRun ?? prev.activeRun,
    liveOutput: liveOutput ?? null,
    previewUrl: delta.previewUrl ?? prev.previewUrl,
    runEvents,
    sandbox: delta.sandbox ?? prev.sandbox,
    previewWake: delta.previewWake ?? prev.previewWake,
  };
}

async function assertProjectOwner(projectId: string, userId: string): Promise<boolean> {
  const proj = await query(
    `SELECT p.id FROM projects p WHERE p.id = $1 AND p.owner_id = $2`,
    [projectId, userId],
  );
  return Boolean(proj.rows[0]);
}

async function loadActiveRunAndMeta(projectId: string): Promise<{
  activeRun: ProjectStreamActiveRun;
  sandbox: ProjectStreamSandbox;
  previewWake: ProjectStreamUpdate["previewWake"];
  previewUrl: string | null;
  liveOutput: string | null;
}> {
  const runs = await query<{ id: string; status: string; live_output: string | null }>(
    `SELECT id, status, live_output FROM agent_runs WHERE project_id = $1 ORDER BY created_at DESC LIMIT 1`,
    [projectId],
  );
  const sandbox = await query<NonNullable<ProjectStreamSandbox>>(`
    SELECT preview_url, provider, external_id, status, name, agent_server_status,
           session_expires_at
    FROM sandboxes WHERE project_id = $1 ORDER BY last_active_at DESC NULLS LAST LIMIT 1`,
    [projectId],
  );
  const wake = await query<{ id: string; status: string }>(
    `SELECT id, status FROM sandbox_wake_requests
     WHERE project_id = $1 AND status IN ('queued', 'running')
     ORDER BY created_at DESC LIMIT 1`,
    [projectId],
  );
  const activeRun = runs.rows[0];
  const sb = sandbox.rows[0] ?? null;
  const previewUrl = sb?.preview_url ?? null;
  const liveOutput =
    activeRun?.status === "running" ? activeRun.live_output ?? null : null;
  return {
    activeRun,
    sandbox: sb,
    previewWake: wake.rows[0] ?? null,
    previewUrl,
    liveOutput,
  };
}

export async function loadProjectStreamSnapshot(
  projectId: string,
  userId: string,
): Promise<ProjectStreamUpdate | null> {
  if (!(await assertProjectOwner(projectId, userId))) return null;

  const msgs = await query<ProjectStreamMessage>(
    `SELECT m.id, m.role, m.content, m.created_at, m.run_id
     FROM messages m
     WHERE m.project_id = $1
     ORDER BY m.created_at DESC LIMIT ${MESSAGE_CAP}`,
    [projectId],
  );

  const meta = await loadActiveRunAndMeta(projectId);
  let runEvents: ProjectStreamRunEvent[] = [];
  const activeRun = meta.activeRun;
  if (activeRun && (activeRun.status === "queued" || activeRun.status === "running")) {
    const ev = await query<RunEventRow>(
      `SELECT seq, event_class, tool_name, payload
       FROM run_events WHERE run_id = $1
       ORDER BY seq ASC`,
      [activeRun.id],
    );
    runEvents = ev.rows.map((row) => toWireEvent(row));
  }

  return {
    messages: [...msgs.rows].reverse(),
    activeRun,
    liveOutput: meta.liveOutput,
    previewUrl: meta.previewUrl,
    runEvents,
    sandbox: meta.sandbox,
    previewWake: meta.previewWake,
  };
}

/** Incremental fetch after LISTEN/NOTIFY (or slow poll). */
export async function loadProjectStreamDelta(
  projectId: string,
  userId: string,
  cursor: ProjectStreamCursor,
): Promise<ProjectStreamUpdate | null> {
  if (!(await assertProjectOwner(projectId, userId))) return null;

  let newMessages: ProjectStreamMessage[] = [];
  if (cursor.lastMessageAt) {
    const msgs = await query<ProjectStreamMessage>(
      `SELECT m.id, m.role, m.content, m.created_at, m.run_id
       FROM messages m
       WHERE m.project_id = $1
         AND (m.created_at > $2::timestamptz
              OR (m.created_at = $2::timestamptz AND ($3::uuid IS NULL OR m.id > $3)))
       ORDER BY m.created_at ASC
       LIMIT ${MESSAGE_CAP}`,
      [projectId, cursor.lastMessageAt, cursor.lastMessageId],
    );
    newMessages = msgs.rows;
  } else {
    const msgs = await query<ProjectStreamMessage>(
      `SELECT m.id, m.role, m.content, m.created_at, m.run_id
       FROM messages m
       WHERE m.project_id = $1
       ORDER BY m.created_at DESC LIMIT ${MESSAGE_CAP}`,
      [projectId],
    );
    newMessages = [...msgs.rows].reverse();
  }

  const meta = await loadActiveRunAndMeta(projectId);
  let runEvents: ProjectStreamRunEvent[] = [];
  const activeRun = meta.activeRun;
  if (activeRun && (activeRun.status === "queued" || activeRun.status === "running")) {
    const sameRun = cursor.activeRunId === activeRun.id;
    const fromSeq = sameRun ? cursor.lastRunEventSeq : -1;
    const ev = await query<RunEventRow>(
      `SELECT seq, event_class, tool_name, payload
       FROM run_events WHERE run_id = $1 AND seq > $2
       ORDER BY seq ASC
       LIMIT 200`,
      [activeRun.id, fromSeq],
    );
    runEvents = ev.rows.map((row) => toWireEvent(row));
  }

  return {
    messages: newMessages,
    activeRun,
    liveOutput: meta.liveOutput,
    previewUrl: meta.previewUrl,
    runEvents,
    sandbox: meta.sandbox,
    previewWake: meta.previewWake,
  };
}

function streamBusy(update: ProjectStreamUpdate): boolean {
  return (
    update.activeRun?.status === "queued" ||
    update.activeRun?.status === "running" ||
    update.previewWake != null
  );
}

/** Slow poll interval when no NOTIFY (safety net). */
export function streamFallbackPollMs(update: ProjectStreamUpdate): number {
  return streamBusy(update) ? 2000 : 15_000;
}