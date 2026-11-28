-- Phone is enough to sign in. Email stays for older accounts. Idempotent.

ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS users_phone_idx ON users (phone) WHERE phone IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_identity_chk') THEN
    ALTER TABLE users
      ADD CONSTRAINT users_identity_chk CHECK (email IS NOT NULL OR phone IS NOT NULL);
  END IF;
END $$;
