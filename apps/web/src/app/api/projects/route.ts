import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { query } from "@/lib/db";

export async function GET() {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const res = await query(
    `SELECT id, title, status, updated_at FROM projects
     WHERE owner_id = $1 AND status <> 'deleted' ORDER BY updated_at DESC`,
    [userId],
  );
  return NextResponse.json({ projects: res.rows });
}

export async function POST(req: Request) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const body = await req.json();
  const title = String(body.title ?? "پروژه جدید").trim();
  const ins = await query<{ id: string }>(
    `INSERT INTO projects (owner_id, title) VALUES ($1, $2) RETURNING id`,
    [userId, title],
  );
  const projectId = ins.rows[0].id;
  await query(
    `INSERT INTO sandboxes (project_id, name, provider, status)
     VALUES ($1, $2, 'local', 'creating')`,
    [projectId, `${process.env.DEPLOY_ENV ?? "dev"}:${projectId}`],
  );
  return NextResponse.json({ id: projectId });
}