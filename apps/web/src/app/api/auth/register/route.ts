import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json({ error: "از ثبت‌نام با کد تأیید استفاده کنید" }, { status: 410 });
}