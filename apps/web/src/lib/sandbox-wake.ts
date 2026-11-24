/** When to enqueue worker preview wake (Vite + Agent Server on Vercel). */

export type SandboxWakeSnapshot = {
  preview_url?: string | null;
  provider?: string | null;
  status?: string | null;
  agent_server_status?: string | null;
} | null;

export function usesVercelRemoteStack(sandbox: SandboxWakeSnapshot): boolean {
  const provider = sandbox?.provider;
  return provider === "vercel" || provider == null;
}

export function needsSandboxStackWake(
  sandbox: SandboxWakeSnapshot,
  previewUrl: string | null,
  options: { busy: boolean; wakeInFlight: boolean },
): boolean {
  if (!usesVercelRemoteStack(sandbox)) return false;
  if (options.busy || options.wakeInFlight) return false;

  const effectivePreview = previewUrl ?? sandbox?.preview_url ?? null;
  const stopped = sandbox?.status === "stopped";
  const noPreview = !effectivePreview;
  const agentNotReady = sandbox?.agent_server_status !== "ready";

  return stopped || noPreview || agentNotReady;
}

/** UI + send gate: Vite up, agent /ready, no wake job in flight. */
export function isSandboxStackReady(
  sandbox: SandboxWakeSnapshot,
  previewUrl: string | null,
  wakeInFlight: boolean,
): boolean {
  if (!usesVercelRemoteStack(sandbox)) return true;
  if (wakeInFlight) return false;
  const effectivePreview = previewUrl ?? sandbox?.preview_url ?? null;
  if (!effectivePreview) return false;
  if (sandbox?.status === "stopped") return false;
  return sandbox?.agent_server_status === "ready";
}