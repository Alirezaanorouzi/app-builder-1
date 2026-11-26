import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/auth";
import { query } from "@/lib/db";

const KEY = /^[a-z][a-z0-9_]{0,63}$/;

export async function GET() {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "not found" }, { status: 404 });
  const res = await query(
    `SELECT key, enabled, note, updated_at FROM feature_flags ORDER BY key`,
  );
  return NextResponse.json({ flags: res.rows });
}

export async function POST(req: Request) {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "not found" }, { status: 404 });
  const body = (await req.json().catch(() => ({}))) as {
    key?: string;
    enabled?: boolean;
    note?: string | null;
  };
  const key = String(body.key ?? "").trim().toLowerCase();
  if (!KEY.test(key)) {
    return NextResponse.json({ error: "invalid key" }, { status: 400 });
  }
  const enabled = body.enabled === true;
  const note = body.note == null ? null : String(body.note).slice(0, 200);
  await query(
    `INSERT INTO feature_flags (key, enabled, note)
     VALUES ($1, $2, COALESCE($3, ''))
     ON CONFLICT (key) DO UPDATE
       SET enabled = EXCLUDED.enabled,
           note = COALESCE($3, feature_flags.note),
           updated_at = now()`,
    [key, enabled, note],
  );
  return NextResponse.json({ ok: true });
}
