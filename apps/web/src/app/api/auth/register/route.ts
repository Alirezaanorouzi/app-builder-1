import { NextResponse } from "next/server";
import { createSession } from "@/lib/auth";
import { query } from "@/lib/db";
import { formatIranMobile, normalizeIranMobile } from "@/lib/phone";

export async function POST(req: Request) {
  const body = await req.json();
  const phone = normalizeIranMobile(String(body.phone ?? ""));
  if (!phone) return NextResponse.json({ error: "شماره موبایل نادرست است" }, { status: 400 });
  try {
    const ins = await query<{ id: string }>(
      `INSERT INTO users (phone, display_name)
       VALUES ($1, $2) RETURNING id`,
      [phone, formatIranMobile(phone)],
    );
    const userId = ins.rows[0].id;
    await query(`INSERT INTO user_limits (user_id) VALUES ($1) ON CONFLICT DO NOTHING`, [userId]);
    await createSession(userId, req.headers.get("user-agent") ?? undefined);
    return NextResponse.json({ ok: true });
  } catch (err) {
    if ((err as { code?: string }).code === "23505") {
      return NextResponse.json({ error: "این شماره قبلاً ثبت شده" }, { status: 409 });
    }
    throw err;
  }
}
