-- Realtime UI: NOTIFY on per-project stream changes (web LISTEN + incremental fetch).

CREATE OR REPLACE FUNCTION notify_builder_project_stream()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  pid uuid;
BEGIN
  IF TG_TABLE_NAME = 'messages' THEN
    pid := NEW.project_id;
  ELSIF TG_TABLE_NAME = 'run_events' THEN
    SELECT ar.project_id INTO pid FROM agent_runs ar WHERE ar.id = NEW.run_id;
  ELSIF TG_TABLE_NAME = 'agent_runs' THEN
    pid := NEW.project_id;
  ELSIF TG_TABLE_NAME = 'sandboxes' THEN
    pid := NEW.project_id;
  ELSIF TG_TABLE_NAME = 'sandbox_wake_requests' THEN
    pid := NEW.project_id;
  ELSE
    RETURN NEW;
  END IF;

  IF pid IS NOT NULL THEN
    PERFORM pg_notify(
      'builder_project_stream',
      json_build_object('project_id', pid, 'table', TG_TABLE_NAME)::text
    );
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_messages_project_stream ON messages;
CREATE TRIGGER trg_messages_project_stream
  AFTER INSERT ON messages
  FOR EACH ROW
  EXECUTE FUNCTION notify_builder_project_stream();

DROP TRIGGER IF EXISTS trg_run_events_project_stream ON run_events;
CREATE TRIGGER trg_run_events_project_stream
  AFTER INSERT ON run_events
  FOR EACH ROW
  EXECUTE FUNCTION notify_builder_project_stream();

DROP TRIGGER IF EXISTS trg_agent_runs_project_stream ON agent_runs;
CREATE TRIGGER trg_agent_runs_project_stream
  AFTER INSERT OR UPDATE OF status, live_output ON agent_runs
  FOR EACH ROW
  EXECUTE FUNCTION notify_builder_project_stream();

DROP TRIGGER IF EXISTS trg_sandboxes_project_stream ON sandboxes;
CREATE TRIGGER trg_sandboxes_project_stream
  AFTER INSERT OR UPDATE ON sandboxes
  FOR EACH ROW
  EXECUTE FUNCTION notify_builder_project_stream();

DROP TRIGGER IF EXISTS trg_wake_project_stream ON sandbox_wake_requests;
CREATE TRIGGER trg_wake_project_stream
  AFTER INSERT OR UPDATE OF status ON sandbox_wake_requests
  FOR EACH ROW
  EXECUTE FUNCTION notify_builder_project_stream();