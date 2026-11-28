-- Phone OTP for Kavenegar lookup. Idempotent.

CREATE TABLE IF NOT EXISTS phone_otp_challenges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose IN ('login', 'signup')),
  code_hash TEXT NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  send_ip INET,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS phone_otp_phone_created_idx
  ON phone_otp_challenges (phone, created_at DESC);

CREATE INDEX IF NOT EXISTS phone_otp_expires_idx
  ON phone_otp_challenges (expires_at)
  WHERE used_at IS NULL;