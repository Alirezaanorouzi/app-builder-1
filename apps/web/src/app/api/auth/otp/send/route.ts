import { NextResponse } from "next/server";
import { otpSendBodySchema } from "@/lib/auth-otp-api";
import { formatIranMobile, normalizeIranMobile } from "@/lib/phone";
import { isKavenegarConfigured, sendKavenegarLookup } from "@/lib/kavenegar";
import {
  OTP_EXPIRES_SEC,
  OTP_RESEND_SEC,
  assertCanSendOtp,
  clientIp,
  createOtpChallenge,
  generateOtpCode,
  revokeOtpChallenge,
} from "@/lib/phone-otp";
import { query } from "@/lib/db";

export async function POST(req: Request) {
  if (!isKavenegarConfigured()) {
    return NextResponse.json({ error: "سرویس پیامک فعال نیست" }, { status: 503 });
  }

  const json = await req.json().catch(() => null);
  const parsed = otpSendBodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ error: "ورودی نامعتبر" }, { status: 400 });
  }

  const phone = normalizeIranMobile(parsed.data.phone);
  const purpose = parsed.data.purpose;
  if (!phone) return NextResponse.json({ error: "شماره موبایل نادرست است" }, { status: 400 });

  const user = await query<{ id: string }>(
    `SELECT id FROM users WHERE phone = $1 AND status = 'active'`,
    [phone],
  );
  const exists = Boolean(user.rows[0]);
  if (purpose === "login" && !exists) {
    return NextResponse.json({ error: "این شماره ثبت نشده؛ ابتدا ثبت‌نام کنید" }, { status: 404 });
  }
  if (purpose === "signup" && exists) {
    return NextResponse.json({ error: "این شماره قبلاً ثبت شده؛ وارد شوید" }, { status: 409 });
  }

  const ip = clientIp(req);
  const rateError = await assertCanSendOtp(phone, ip);
  if (rateError) return NextResponse.json({ error: rateError }, { status: 429 });

  const code = generateOtpCode();
  const { challengeId, expiresAt } = await createOtpChallenge(phone, purpose, code, ip);

  const sent = await sendKavenegarLookup(phone, code);
  if (!sent.ok) {
    await revokeOtpChallenge(challengeId);
    const status = sent.status === 418 || sent.status === 424 ? 503 : 502;
    return NextResponse.json({ error: sent.message }, { status });
  }

  return NextResponse.json({
    challengeId,
    phoneDisplay: formatIranMobile(phone),
    resendAfterSec: OTP_RESEND_SEC,
    expiresInSec: OTP_EXPIRES_SEC,
    expiresAt,
  });
}