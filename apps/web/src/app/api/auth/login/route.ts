import { NextResponse } from "next/server";
import { createSession } from "@/lib/auth";
import { query } from "@/lib/db";
import { normalizeIranMobile } from "@/lib/phone";
import { projectAfterLogin } from "@/lib/project-bootstrap";

export async function POST(req: Request) {
  const body = await req.json();
  const phone = normalizeIranMobile(String(body.phone ?? ""));
  if (!phone) return NextResponse.json({ error: "شماره موبایل نادرست است" }, { status: 400 });
  const res = await query<{ id: string }>(
    `SELECT id FROM users WHERE phone = $1 AND status = 'active'`,
    [phone],
  );
  const user = res.rows[0];
  if (!user) return NextResponse.json({ error: "این شماره ثبت نشده" }, { status: 401 });
  await createSession(user.id, req.headers.get("user-agent") ?? undefined);
  const projectId = await projectAfterLogin(user.id);
  return NextResponse.json({ ok: true, projectId });
}
