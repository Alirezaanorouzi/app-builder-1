import { createHmac, randomInt, randomUUID, timingSafeEqual } from "crypto";
import { query } from "@/lib/db";

const OTP_TTL_MS = 5 * 60 * 1000;
const RESEND_GAP_MS = 60 * 1000;
const MAX_SENDS_PER_HOUR = 8;
const MAX_VERIFY_ATTEMPTS = 5;

export type OtpPurpose = "login" | "signup";

function otpPepper(): string {
  const secret = process.env.OTP_SECRET?.trim() || process.env.SESSION_SECRET?.trim();
  if (!secret) throw new Error("OTP_SECRET or SESSION_SECRET is required");
  return secret;
}

export function generateOtpCode(): string {
  return String(randomInt(100_000, 1_000_000));
}

export function hashOtpCode(challengeId: string, phone: string, code: string): string {
  return createHmac("sha256", otpPepper())
    .update(`${challengeId}|${phone}|${code}`)
    .digest("hex");
}

function constantTimeEqualHex(a: string, b: string): boolean {
  try {
    const left = Buffer.from(a, "hex");
    const right = Buffer.from(b, "hex");
    if (left.length !== right.length) return false;
    return timingSafeEqual(left, right);
  } catch {
    return false;
  }
}

export function clientIp(req: Request): string | null {
  const forwarded = req.headers.get("x-forwarded-for");
  const raw = (forwarded ? forwarded.split(",")[0] : req.headers.get("x-real-ip"))?.trim() || null;
  if (!raw) return null;
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(raw) || /^[0-9a-f:]+$/i.test(raw)) return raw;
  return null;
}

export async function assertCanSendOtp(phone: string, ip: string | null): Promise<string | null> {
  const hourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  const recent = await query<{ n: string }>(
    `SELECT count(*)::text AS n FROM phone_otp_challenges
     WHERE phone = $1 AND created_at > $2`,
    [phone, hourAgo],
  );
  if (Number(recent.rows[0]?.n ?? 0) >= MAX_SENDS_PER_HOUR) {
    return "درخواست‌های زیاد؛ یک ساعت بعد دوباره امتحان کنید";
  }

  const last = await query<{ created_at: Date }>(
    `SELECT created_at FROM phone_otp_challenges
     WHERE phone = $1
     ORDER BY created_at DESC
     LIMIT 1`,
    [phone],
  );
  const lastAt = last.rows[0]?.created_at?.getTime();
  if (lastAt && Date.now() - lastAt < RESEND_GAP_MS) {
    return "لطفاً یک دقیقه صبر کنید و دوباره درخواست دهید";
  }

  if (ip) {
    const ipRecent = await query<{ n: string }>(
      `SELECT count(*)::text AS n FROM phone_otp_challenges
       WHERE send_ip = $1::inet AND created_at > $2`,
      [ip, hourAgo],
    );
    if (Number(ipRecent.rows[0]?.n ?? 0) >= MAX_SENDS_PER_HOUR * 2) {
      return "درخواست‌های زیاد از این شبکه";
    }
  }

  return null;
}

export async function createOtpChallenge(
  phone: string,
  purpose: OtpPurpose,
  code: string,
  ip: string | null,
): Promise<{ challengeId: string; expiresAt: string }> {
  const expiresAt = new Date(Date.now() + OTP_TTL_MS);
  const challengeId = randomUUID();
  const codeHash = hashOtpCode(challengeId, phone, code);
  await query(
    `UPDATE phone_otp_challenges SET used_at = now()
     WHERE phone = $1 AND used_at IS NULL`,
    [phone],
  );
  await query(
    `INSERT INTO phone_otp_challenges (id, phone, purpose, code_hash, expires_at, send_ip)
     VALUES ($1, $2, $3, $4, $5, $6::inet)`,
    [challengeId, phone, purpose, codeHash, expiresAt.toISOString(), ip],
  );
  return { challengeId, expiresAt: expiresAt.toISOString() };
}

/** Drop SMS challenge when provider send fails so a fresh code can be requested. */
export async function revokeOtpChallenge(challengeId: string): Promise<void> {
  await query(
    `UPDATE phone_otp_challenges SET used_at = now()
     WHERE id = $1 AND used_at IS NULL`,
    [challengeId],
  );
}

export async function verifyOtpChallenge(
  challengeId: string,
  code: string,
  purpose: OtpPurpose,
): Promise<
  | { ok: true; phone: string }
  | { ok: false; error: string; httpStatus: number }
> {
  const res = await query<{
    phone: string;
    purpose: OtpPurpose;
    code_hash: string;
    attempts: number;
    expires_at: Date;
    used_at: Date | null;
  }>(
    `SELECT phone, purpose, code_hash, attempts, expires_at, used_at
     FROM phone_otp_challenges WHERE id = $1`,
    [challengeId],
  );
  const row = res.rows[0];
  if (!row || row.used_at) {
    return { ok: false, error: "کد نامعتبر است", httpStatus: 400 };
  }
  if (row.purpose !== purpose) {
    return { ok: false, error: "کد نامعتبر است", httpStatus: 400 };
  }
  if (row.expires_at.getTime() < Date.now()) {
    return { ok: false, error: "کد منقضی شده؛ دوباره درخواست دهید", httpStatus: 400 };
  }
  if (row.attempts >= MAX_VERIFY_ATTEMPTS) {
    await query(`UPDATE phone_otp_challenges SET used_at = now() WHERE id = $1`, [challengeId]);
    return { ok: false, error: "تلاش‌های زیاد؛ کد جدید بگیرید", httpStatus: 429 };
  }

  const expected = hashOtpCode(challengeId, row.phone, code);
  const valid = constantTimeEqualHex(expected, row.code_hash);

  if (!valid) {
    const bumped = await query<{ attempts: number }>(
      `UPDATE phone_otp_challenges SET attempts = attempts + 1 WHERE id = $1 RETURNING attempts`,
      [challengeId],
    );
    if ((bumped.rows[0]?.attempts ?? 0) >= MAX_VERIFY_ATTEMPTS) {
      await query(`UPDATE phone_otp_challenges SET used_at = now() WHERE id = $1`, [challengeId]);
    }
    return { ok: false, error: "کد نادرست است", httpStatus: 401 };
  }

  await query(`UPDATE phone_otp_challenges SET used_at = now() WHERE id = $1`, [challengeId]);
  return { ok: true, phone: row.phone };
}

export const OTP_RESEND_SEC = RESEND_GAP_MS / 1000;
export const OTP_EXPIRES_SEC = OTP_TTL_MS / 1000;