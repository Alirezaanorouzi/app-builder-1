import { NextResponse } from "next/server";
import { createSession, verifyPassword } from "@/lib/auth";
import { query } from "@/lib/db";

export async function POST(req: Request) {
  const body = await req.json();
  const email = String(body.email ?? "").trim().toLowerCase();
  const password = String(body.password ?? "");
  const res = await query<{ id: string; password_hash: string }>(
    `SELECT id, password_hash FROM users WHERE email = $1 AND status = 'active'`,
    [email],
  );
  const user = res.rows[0];
  if (!user || !(await verifyPassword(user.password_hash, password))) {
    return NextResponse.json({ error: "ایمیل یا رمز نادرست" }, { status: 401 });
  }
  await createSession(user.id, req.headers.get("user-agent") ?? undefined);
  return NextResponse.json({ ok: true });
}