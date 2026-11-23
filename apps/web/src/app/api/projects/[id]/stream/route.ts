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
  let interval: ReturnType<typeof setInterval> | undefined;
  const stream = new ReadableStream({
    async start(controller) {
      let lastSnapshot = "";
      const send = (event: string, data: unknown) => {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };
      const tick = async () => {
        const proj = await query(
          `SELECT p.id FROM projects p WHERE p.id = $1 AND p.owner_id = $2`,
          [projectId, userId],
        );
        if (!proj.rows[0]) return;

        const msgs = await query(
          `SELECT m.id, m.role, m.content, m.created_at, m.run_id
           FROM messages m
           WHERE m.project_id = $1
           ORDER BY m.created_at DESC LIMIT 50`,
          [projectId],
        );
        const runs = await query<{ id: string; status: string }>(
          `SELECT id, status FROM agent_runs WHERE project_id = $1 ORDER BY created_at DESC LIMIT 1`,
          [projectId],
        );
        const sandbox = await query<{
          preview_url: string | null;
          provider: string | null;
          external_id: string | null;
          status: string | null;
          name: string | null;
        }>(
          `SELECT preview_url, provider, external_id, status, name
           FROM sandboxes WHERE project_id = $1 ORDER BY last_active_at DESC NULLS LAST LIMIT 1`,
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
        const snapshot = JSON.stringify({
          msgs: msgs.rows,
          run: activeRun,
          previewUrl,
          runEvents,
          sandbox: sb,
        });
        if (snapshot !== lastSnapshot) {
          lastSnapshot = snapshot;
          send("update", {
            messages: [...msgs.rows].reverse(),
            activeRun,
            previewUrl,
            runEvents,
            sandbox: sb ?? null,
          });
        }
      };
      await tick();
      interval = setInterval(() => {
        tick().catch(() => controller.close());
      }, 1000);
    },
    cancel() {
      if (interval) clearInterval(interval);
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