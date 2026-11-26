import { hash, verify } from "@node-rs/argon2";
import { cookies } from "next/headers";
import { createHash, randomBytes } from "crypto";
import { query } from "./db";

const SESSION_COOKIE = "ab_session";
const SESSION_DAYS = 30;

export async function hashPassword(password: string) {
  return hash(password, { memoryCost: 19456, timeCost: 2, parallelism: 1 });
}

export async function verifyPassword(hashStr: string, password: string) {
  return verify(hashStr, password);
}

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

/** Logged-in user whose email is listed in ADMIN_EMAILS. */
export async function requireAdmin(): Promise<{ id: string; email: string } | null> {
  const userId = await getSessionUserId();
  if (!userId) return null;
  const allow = adminEmails();
  if (allow.size === 0) return null;
  const res = await query<{ email: string }>(
    `SELECT email::text AS email FROM users WHERE id = $1 AND status = 'active'`,
    [userId],
  );
  const email = res.rows[0]?.email?.trim().toLowerCase();
  if (!email || !allow.has(email)) return null;
  return { id: userId, email };
}