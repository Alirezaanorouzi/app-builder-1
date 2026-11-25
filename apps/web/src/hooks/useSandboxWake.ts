import { useCallback, useRef } from "react";
import { needsSandboxStackWake, type SandboxWakeSnapshot } from "@/lib/sandbox-wake";

const MIN_WAKE_INTERVAL_MS = 30_000;

export type SandboxWakeControls = {
  /** POST /sandbox/wake when the stack is not ready (throttled). */
  requestWake: () => void;
};

/**
 * Enqueue sandbox wake when the project needs Vite + Agent Server (Vercel remote).
 * Runs on project open (chat or preview), not only the preview tab.
 */
export function useSandboxWake(
  projectId: string,
  sandbox: SandboxWakeSnapshot,
  previewUrl: string | null,
  options: { busy: boolean; wakeInFlight: boolean },
): SandboxWakeControls {
  const lastWakeAt = useRef(0);

  const requestWake = useCallback(() => {
    if (!needsSandboxStackWake(sandbox, previewUrl, options)) return;
    const now = Date.now();
    if (now - lastWakeAt.current < MIN_WAKE_INTERVAL_MS) return;
    lastWakeAt.current = now;
    void fetch(`/api/projects/${projectId}/sandbox/wake`, { method: "POST" }).catch(() => {
      lastWakeAt.current = 0;
    });
  }, [projectId, sandbox, previewUrl, options.busy, options.wakeInFlight]);

  return { requestWake };
}