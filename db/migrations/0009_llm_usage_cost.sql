-- Per-call Liara cost on the existing usage ledger. Idempotent.

ALTER TABLE usage_ledger
  ADD COLUMN IF NOT EXISTS cache_read_tokens INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reasoning_tokens INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cost_toman NUMERIC(18, 4) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS provider_response_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS usage_ledger_run_response_idx
  ON usage_ledger (run_id, provider_response_id)
  WHERE provider_response_id IS NOT NULL AND provider_response_id <> '';
