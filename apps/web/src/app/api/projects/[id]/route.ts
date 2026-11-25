import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { query } from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await params;
  const res = await query(
    `SELECT p.*,
            s.preview_url,
            s.provider,
            s.external_id,
            s.name AS sandbox_name,
            s.status AS sandbox_status,
            s.agent_server_status,
            s.session_expires_at
     FROM projects p
     LEFT JOIN sandboxes s ON s.project_id = p.id
     WHERE p.id = $1 AND p.owner_id = $2`,
    [id, userId],
  );
  if (!res.rows[0]) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json(res.rows[0]);
}