import { getSessionUserId } from "@/lib/auth";
import { query } from "@/lib/db";
import { summarizeRunEvent, type RunEventRow } from "@/lib/run-events";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return new Response("unauthorized", { status: 401 });
  const { id: projectId } = await params;

  const encoder = new TextEncoder();
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  const stream = new ReadableStream({
    async start(controller) {
      let lastSnapshot = "";
      let pollMs = 1000;
      const send = (event: string, data: unknown) => {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };
      const tick = async (): Promise<number> => {
        const proj = await query(
          `SELECT p.id FROM projects p WHERE p.id = $1 AND p.owner_id = $2`,
          [projectId, userId],
        );
        if (!proj.rows[0]) return pollMs;

        const msgs = await query(
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
        let runEvents: Array<RunEventRow & { summary: string }> = [];
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
        const snapshot = JSON.stringify({
          msgs: msgs.rows,
          run: activeRun,
          liveOutput,
          previewUrl,
          runEvents,
          sandbox: sb,
          previewWake,
        });
        if (snapshot !== lastSnapshot) {
          lastSnapshot = snapshot;
          send("update", {
            messages: [...msgs.rows].reverse(),
            activeRun,
            liveOutput,
            previewUrl,
            runEvents,
            sandbox: sb ?? null,
            previewWake,
          });
        }
        const active =
          activeRun?.status === "queued" || activeRun?.status === "running" || previewWake != null;
        return active ? 200 : 1000;
      };
      const schedule = () => {
        pollTimer = setTimeout(() => {
          tick()
            .then((next) => {
              pollMs = next;
              schedule();
            })
            .catch(() => controller.close());
        }, pollMs);
      };
      pollMs = await tick();
      schedule();
    },
    cancel() {
      if (pollTimer) clearTimeout(pollTimer);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}