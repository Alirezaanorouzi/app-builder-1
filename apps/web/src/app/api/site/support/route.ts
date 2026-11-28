import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { formatIranMobile, normalizeIranMobile } from "@/lib/phone";

export async function GET() {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const normalized = normalizeIranMobile(process.env.PHONE_NUMBER ?? "");
  if (!normalized) {
    return NextResponse.json({ phone: null, tel: null });
  }
  return NextResponse.json({
    phone: formatIranMobile(normalized),
    tel: `+${normalized}`,
  });
}