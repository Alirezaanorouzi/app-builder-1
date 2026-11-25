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

export type ProjectStreamRunEvent = RunEventRow & { summary: string };

export type ProjectStreamSandbox = {
  preview_url: string | null;
  provider: string | null;
  external_id: string | null;
  status: string | null;
  name: string | null;
  agent_server_status: string | null;
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

export async function loadProjectStreamSnapshot(
  projectId: string,
  userId: string,
): Promise<ProjectStreamUpdate | null> {
  const proj = await query(
    `SELECT p.id FROM projects p WHERE p.id = $1 AND p.owner_id = $2`,
    [projectId, userId],
  );
  if (!proj.rows[0]) return null;

  const msgs = await query<ProjectStreamMessage>(
    `SELECT m.id, m.role, m.content, m.created_at, m.run_id
     FROM messages m
     WHERE m.project_id = $1
     ORDER BY m.created_at DESC LIMIT 50`,
    [projectId],
  );
  const runs = await query<{ id: string; status: string; live_output: string | null }>(
    `SELECT id, status, live_output FROM agent_runs WHERE project_id = $1 ORDER BY created_at DESC LIMIT 1`,
    [projectId],
  );
  const sandbox = await query<{
    preview_url: string | null;
    provider: string | null;
    external_id: string | null;
    status: string | null;
    name: string | null;
    agent_server_status: string | null;
  }>(
    `SELECT preview_url, provider, external_id, status, name, agent_server_status
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
  let runEvents: ProjectStreamRunEvent[] = [];
  if (activeRun && (activeRun.status === "queued" || activeRun.status === "running")) {
    const ev = await query<RunEventRow>(
      `SELECT seq, event_class, tool_name, payload
       FROM run_events WHERE run_id = $1
       ORDER BY seq ASC`,
      [activeRun.id],
    );
    runEvents = ev.rows.map((row) => ({
      ...row,
      summary: summarizeRunEvent(row),
    }));
  }
  const sb = sandbox.rows[0];
  const previewUrl = sb?.preview_url ?? null;
  const previewWake = wake.rows[0] ?? null;
  const liveOutput =
    activeRun?.status === "running" ? activeRun.live_output ?? null : null;
  return {
    messages: [...msgs.rows].reverse(),
    activeRun,
    liveOutput,
    previewUrl,
    runEvents,
    sandbox: sb ?? null,
    previewWake,
  };
}

function streamPollMs(update: ProjectStreamUpdate): number {
  const active =
    update.activeRun?.status === "queued" ||
    update.activeRun?.status === "running" ||
    update.previewWake != null;
  return active ? 200 : 1000;
}

function snapshotKey(update: ProjectStreamUpdate): string {
  return JSON.stringify({
    msgs: update.messages,
    run: update.activeRun,
    liveOutput: update.liveOutput,
    previewUrl: update.previewUrl,
    runEvents: update.runEvents,
    sandbox: update.sandbox,
    previewWake: update.previewWake,
  });
}

/** Poll interval (ms) returned by tick: faster while a run or wake is in flight. */
export async function tickProjectStream(
  projectId: string,
  userId: string,
  lastSnapshot: string,
): Promise<{ pollMs: number; snapshot: string; update: ProjectStreamUpdate | null }> {
  const update = await loadProjectStreamSnapshot(projectId, userId);
  if (!update) {
    return { pollMs: 1000, snapshot: lastSnapshot, update: null };
  }
  const snapshot = snapshotKey(update);
  if (snapshot === lastSnapshot) {
    return { pollMs: streamPollMs(update), snapshot, update: null };
  }
  return { pollMs: streamPollMs(update), snapshot, update };
}