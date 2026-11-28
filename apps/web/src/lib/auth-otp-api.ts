import { z } from "zod";

export const otpPurposeSchema = z.enum(["login", "signup"]);

export const otpSendBodySchema = z.object({
  phone: z.string().trim().min(8).max(32),
  purpose: otpPurposeSchema,
});

export const otpVerifyBodySchema = z.object({
  challengeId: z.string().uuid(),
  code: z.string().trim().min(4).max(12),
  purpose: otpPurposeSchema,
});

export type OtpSendBody = z.infer<typeof otpSendBodySchema>;
export type OtpVerifyBody = z.infer<typeof otpVerifyBodySchema>;

export function parseOtpCode(raw: string): string | null {
  const digits = raw.replace(/\D/g, "");
  if (!/^\d{6}$/.test(digits)) return null;
  return digits;
}