import { NextResponse } from "next/server";
import { hashPassword, createSession } from "@/lib/auth";
import { query } from "@/lib/db";

export async function POST(req: Request) {
  const body = await req.json();
  const email = String(body.email ?? "").trim().toLowerCase();
  const password = String(body.password ?? "");
  const displayName = String(body.displayName ?? "").trim() || email.split("@")[0];
  if (!email || password.length < 8) {
    return NextResponse.json({ error: "ورودی نامعتبر" }, { status: 400 });
  }
  const passwordHash = await hashPassword(password);
  try {
    const ins = await query<{ id: string }>(
      `INSERT INTO users (email, password_hash, display_name)
       VALUES ($1, $2, $3) RETURNING id`,
      [email, passwordHash, displayName],
    );
    const userId = ins.rows[0].id;
    await query(`INSERT INTO user_limits (user_id) VALUES ($1) ON CONFLICT DO NOTHING`, [userId]);
    await createSession(userId, req.headers.get("user-agent") ?? undefined);
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "ایمیل تکراری است" }, { status: 409 });
  }
}