-- Run executor visibility (avoid failing runs stuck in thread-pool queue).
ALTER TABLE agent_runs
  ADD COLUMN IF NOT EXISTS execution_started_at TIMESTAMPTZ;

-- Approximate Vercel session deadline for UI/worker without HTTP on every page load.
ALTER TABLE sandboxes
  ADD COLUMN IF NOT EXISTS session_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS agent_runs_stale_idx
  ON agent_runs (status, execution_started_at, heartbeat_at)
  WHERE status = 'running';