-- Incremental assistant token stream while a run is active (SSE).
ALTER TABLE agent_runs
  ADD COLUMN IF NOT EXISTS live_output TEXT;