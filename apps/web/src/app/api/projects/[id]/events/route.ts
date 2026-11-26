import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { query } from "@/lib/db";

const NAMES = new Set(["preview_open", "preview_copy"]);

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await params;
  const body = (await req.json().catch(() => ({}))) as { name?: string };
  const name = String(body.name ?? "");
  if (!NAMES.has(name)) {
    return NextResponse.json({ error: "invalid event" }, { status: 400 });
  }
  const owned = await query(
    `SELECT id FROM projects WHERE id = $1 AND owner_id = $2 AND status <> 'deleted'`,
    [id, userId],
  );
  if (!owned.rows[0]) return NextResponse.json({ error: "not found" }, { status: 404 });
  await query(
    `INSERT INTO product_events (user_id, project_id, name) VALUES ($1, $2, $3)`,
    [userId, id, name],
  );
  return NextResponse.json({ ok: true });
}
