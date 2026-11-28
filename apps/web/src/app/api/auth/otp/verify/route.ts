import { NextResponse } from "next/server";
import { otpVerifyBodySchema, parseOtpCode } from "@/lib/auth-otp-api";
import { finishPhoneAuth } from "@/lib/phone-auth";
import { verifyOtpChallenge } from "@/lib/phone-otp";

export async function POST(req: Request) {
  const json = await req.json().catch(() => null);
  const parsed = otpVerifyBodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ error: "ورودی نامعتبر" }, { status: 400 });
  }

  const code = parseOtpCode(parsed.data.code);
  if (!code) {
    return NextResponse.json({ error: "کد باید ۶ رقم باشد" }, { status: 400 });
  }

  const checked = await verifyOtpChallenge(parsed.data.challengeId, code, parsed.data.purpose);
  if (!checked.ok) {
    return NextResponse.json({ error: checked.error }, { status: checked.httpStatus });
  }

  const auth = await finishPhoneAuth(
    checked.phone,
    parsed.data.purpose,
    req.headers.get("user-agent") ?? undefined,
    parsed.data.displayName,
  );
  if ("error" in auth) {
    return NextResponse.json({ error: auth.error }, { status: auth.httpStatus });
  }

  return NextResponse.json({ ok: true, projectId: auth.projectId });
}