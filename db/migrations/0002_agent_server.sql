-- Agent Server in Vercel Sandbox + run-scoped LLM proxy keys
ALTER TABLE sandboxes
  ADD COLUMN IF NOT EXISTS agent_server_url TEXT,
  ADD COLUMN IF NOT EXISTS agent_session_api_key TEXT,
  ADD COLUMN IF NOT EXISTS agent_server_status TEXT
    CHECK (agent_server_status IS NULL OR agent_server_status IN ('starting', 'ready', 'failed'));

ALTER TABLE agent_runs
  ADD COLUMN IF NOT EXISTS conversation_id UUID,
  ADD COLUMN IF NOT EXISTS llm_proxy_key_id TEXT,
  ADD COLUMN IF NOT EXISTS remote_stopped_at TIMESTAMPTZ;

UPDATE agent_runs ar
SET conversation_id = p.conversation_id
FROM projects p
WHERE ar.conversation_id IS NULL AND ar.project_id = p.id;