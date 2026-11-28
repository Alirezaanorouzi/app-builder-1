import { cookies } from "next/headers";
import { createHash, randomBytes } from "crypto";
import { query } from "./db";
import { normalizeIranMobile } from "./phone";

const SESSION_COOKIE = "ab_session";
const SESSION_DAYS = 30;

function sha256(value: string) {
  return createHash("sha256").update(value).digest("hex");
}

export async function createSession(userId: string, userAgent?: string) {
  const token = randomBytes(32).toString("hex");
  const tokenHash = sha256(token);
  const expires = new Date(Date.now() + SESSION_DAYS * 86400 * 1000);
  await query(
    `INSERT INTO sessions (user_id, token_hash, user_agent, expires_at) VALUES ($1, $2, $3, $4)`,
    [userId, tokenHash, userAgent ?? null, expires.toISOString()],
  );
  const jar = await cookies();
  jar.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires,
  });
}

export async function destroySession() {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (token) {
    await query(`UPDATE sessions SET revoked_at = now() WHERE token_hash = $1`, [sha256(token)]);
    jar.delete(SESSION_COOKIE);
  }
}

export async function getSessionUserId(): Promise<string | null> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const res = await query<{ user_id: string }>(
    `SELECT user_id FROM sessions
     WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > now()`,
    [sha256(token)],
  );
  return res.rows[0]?.user_id ?? null;
}

function adminEmails(): Set<string> {
  return new Set(
    (process.env.ADMIN_EMAILS ?? "")
      .split(",")
      .map((email) => email.trim().toLowerCase())
      .filter(Boolean),
  );
}

function adminPhones(): Set<string> {
  const out = new Set<string>();
  for (const part of (process.env.ADMIN_PHONES ?? "").split(",")) {
    const normalized = normalizeIranMobile(part.trim());
    if (normalized) out.add(normalized);
  }
  return out;
}

/** Logged-in user listed in ADMIN_EMAILS and/or ADMIN_PHONES. */
export async function requireAdmin(): Promise<{ id: string } | null> {
  const userId = await getSessionUserId();
  if (!userId) return null;
  const emails = adminEmails();
  const phones = adminPhones();
  if (emails.size === 0 && phones.size === 0) return null;
  const res = await query<{ email: string | null; phone: string | null }>(
    `SELECT email::text AS email, phone FROM users WHERE id = $1 AND status = 'active'`,
    [userId],
  );
  const row = res.rows[0];
  if (!row) return null;
  const email = row.email?.trim().toLowerCase();
  const phone = row.phone ? normalizeIranMobile(row.phone) : null;
  if (email && emails.has(email)) return { id: userId };
  if (phone && phones.has(phone)) return { id: userId };
  return null;
}