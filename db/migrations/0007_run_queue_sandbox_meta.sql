-- Queue wake channel (not builder_project_stream: that fires on every live_output flush).
-- Sandbox metadata for a real session deadline, entry upload skip, and follow-up seeds.

ALTER TABLE sandboxes
  ADD COLUMN IF NOT EXISTS runtime_session_id TEXT,
  ADD COLUMN IF NOT EXISTS agent_entry_sha TEXT,
  ADD COLUMN IF NOT EXISTS workspace_manifest TEXT;

CREATE OR REPLACE FUNCTION notify_agent_run_queued()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM pg_notify('agent_run_queued', NEW.id::text);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_agent_runs_queued ON agent_runs;
CREATE TRIGGER trg_agent_runs_queued
  AFTER INSERT ON agent_runs
  FOR EACH ROW
  WHEN (NEW.status = 'queued')
  EXECUTE FUNCTION notify_agent_run_queued();

CREATE OR REPLACE FUNCTION notify_sandbox_wake_queued()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM pg_notify('sandbox_wake_queued', NEW.id::text);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sandbox_wake_queued ON sandbox_wake_requests;
CREATE TRIGGER trg_sandbox_wake_queued
  AFTER INSERT ON sandbox_wake_requests
  FOR EACH ROW
  WHEN (NEW.status = 'queued')
  EXECUTE FUNCTION notify_sandbox_wake_queued();
