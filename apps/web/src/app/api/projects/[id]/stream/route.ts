import { getSessionUserId } from "@/lib/auth";
import { getPool } from "@/lib/db";
import type { PoolClient } from "pg";
import {
  cursorFromSnapshot,
  loadProjectStreamDelta,
  loadProjectStreamSnapshot,
  mergeProjectStreamUpdates,
  PROJECT_STREAM_NOTIFY_CHANNEL,
  streamFallbackPollMs,
  type ProjectStreamCursor,
  type ProjectStreamUpdate,
} from "@/lib/project-stream-snapshot";

const KEEPALIVE_MS = 20_000;
const NOTIFY_DEBOUNCE_MS = 40;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return new Response("unauthorized", { status: 401 });
  const { id: projectId } = await params;

  const encoder = new TextEncoder();
  let listenClient: PoolClient | undefined;
  let keepaliveTimer: ReturnType<typeof setInterval> | undefined;
  let fallbackTimer: ReturnType<typeof setTimeout> | undefined;
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        if (closed) return;
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
        );
      };

      let state: ProjectStreamUpdate | null = await loadProjectStreamSnapshot(
        projectId,
        userId,
      );
      if (!state) {
        controller.close();
        return;
      }
      let cursor: ProjectStreamCursor = cursorFromSnapshot(state);
      send("update", state);

      const pushDelta = async () => {
        if (closed) return;
        try {
          const delta = await loadProjectStreamDelta(projectId, userId, cursor);
          if (!delta) return;
          state = mergeProjectStreamUpdates(state!, delta);
          cursor = cursorFromSnapshot(state);
          send("update", state);
        } catch {
          /* next notify or fallback will retry */
        }
      };

      const scheduleDebouncedPush = () => {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          void pushDelta();
        }, NOTIFY_DEBOUNCE_MS);
      };

      const scheduleFallback = () => {
        if (fallbackTimer) clearTimeout(fallbackTimer);
        const pollMs = streamFallbackPollMs(state!);
        fallbackTimer = setTimeout(() => {
          void pushDelta().finally(scheduleFallback);
        }, pollMs);
      };

      listenClient = await getPool().connect();
      try {
        listenClient.on("notification", (msg) => {
          if (msg.channel !== PROJECT_STREAM_NOTIFY_CHANNEL || !msg.payload) return;
          try {
            const payload = JSON.parse(msg.payload) as { project_id?: string };
            if (payload.project_id !== projectId) return;
          } catch {
            return;
          }
          scheduleDebouncedPush();
        });
        await listenClient.query(`LISTEN ${PROJECT_STREAM_NOTIFY_CHANNEL}`);
      } catch {
        /* NOTIFY optional — fallback polling still works */
      }

      keepaliveTimer = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(`event: ping\ndata: {}\n\n`));
        } catch {
          if (keepaliveTimer) clearInterval(keepaliveTimer);
        }
      }, KEEPALIVE_MS);

      scheduleFallback();
    },
    cancel() {
      closed = true;
      if (keepaliveTimer) clearInterval(keepaliveTimer);
      if (fallbackTimer) clearTimeout(fallbackTimer);
      if (debounceTimer) clearTimeout(debounceTimer);
      listenClient
        ?.query(`UNLISTEN ${PROJECT_STREAM_NOTIFY_CHANNEL}`)
        .catch(() => undefined)
        .finally(() => listenClient?.release());
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}