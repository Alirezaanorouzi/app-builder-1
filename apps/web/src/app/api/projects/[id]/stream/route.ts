import { getSessionUserId } from "@/lib/auth";
import { tickProjectStream } from "@/lib/project-stream-snapshot";

const KEEPALIVE_MS = 20_000;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return new Response("unauthorized", { status: 401 });
  const { id: projectId } = await params;

  const encoder = new TextEncoder();
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  let keepaliveTimer: ReturnType<typeof setInterval> | undefined;
  const stream = new ReadableStream({
    async start(controller) {
      let lastSnapshot = "";
      let pollMs = 1000;
      const send = (event: string, data: unknown) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
        );
      };
      const tick = async (): Promise<number> => {
        const { pollMs: nextMs, snapshot, update } = await tickProjectStream(
          projectId,
          userId,
          lastSnapshot,
        );
        lastSnapshot = snapshot;
        if (update) {
          send("update", update);
        }
        return nextMs;
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
      keepaliveTimer = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(`event: ping\ndata: {}\n\n`));
        } catch {
          if (keepaliveTimer) clearInterval(keepaliveTimer);
        }
      }, KEEPALIVE_MS);
      pollMs = await tick();
      schedule();
    },
    cancel() {
      if (pollTimer) clearTimeout(pollTimer);
      if (keepaliveTimer) clearInterval(keepaliveTimer);
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