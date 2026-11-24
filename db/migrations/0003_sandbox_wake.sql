-- Preview wake jobs (resume Vercel sandbox + Vite only — no agent run)
CREATE TABLE sandbox_wake_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  worker_id TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX sandbox_wake_one_active_per_project
  ON sandbox_wake_requests (project_id)
  WHERE status IN ('queued', 'running');

CREATE INDEX sandbox_wake_queued_idx
  ON sandbox_wake_requests (created_at)
  WHERE status = 'queued';