import { createSession } from "@/lib/auth";
import { query } from "@/lib/db";
import { formatIranMobile, normalizeIranMobile } from "@/lib/phone";
import { projectAfterLogin, projectAfterSignup } from "@/lib/project-bootstrap";
import type { OtpPurpose } from "@/lib/phone-otp";

export async function finishPhoneAuth(
  phone: string,
  purpose: OtpPurpose,
  userAgent?: string,
  displayName?: string,
): Promise<{ projectId: string } | { error: string; httpStatus: number }> {
  const stored = normalizeIranMobile(phone);
  if (!stored) return { error: "شماره موبایل نادرست است", httpStatus: 400 };

  const existing = await query<{ id: string }>(
    `SELECT id FROM users WHERE phone = $1 AND status = 'active'`,
    [stored],
  );
  const user = existing.rows[0];

  if (purpose === "login") {
    if (!user) return { error: "این شماره ثبت نشده", httpStatus: 401 };
    await createSession(user.id, userAgent);
    const projectId = await projectAfterLogin(user.id);
    return { projectId };
  }

  if (user) return { error: "این شماره قبلاً ثبت شده", httpStatus: 409 };

  const name = displayName?.trim() || formatIranMobile(stored);

  try {
    const ins = await query<{ id: string }>(
      `INSERT INTO users (phone, display_name) VALUES ($1, $2) RETURNING id`,
      [stored, name],
    );
    const userId = ins.rows[0].id;
    await query(`INSERT INTO user_limits (user_id) VALUES ($1) ON CONFLICT DO NOTHING`, [userId]);
    await createSession(userId, userAgent);
    const projectId = await projectAfterSignup(userId);
    return { projectId };
  } catch (err) {
    if ((err as { code?: string }).code === "23505") {
      return { error: "این شماره قبلاً ثبت شده", httpStatus: 409 };
    }
    throw err;
  }
}