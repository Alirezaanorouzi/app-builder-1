import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { query } from "@/lib/db";
import { listLiaraModelsFromEnv, pickLiaraModel } from "@/lib/liara-models";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id: projectId } = await params;
  const body = await req.json();
  const content = String(body.content ?? "").trim();
  const defaultModel =
    process.env.NEXT_PUBLIC_DEFAULT_MODEL?.trim() ??
    listLiaraModelsFromEnv()[0] ??
    "deepseek/deepseek-v4.1-flash-1017";
  const model = pickLiaraModel(
    body.model != null ? String(body.model) : null,
    defaultModel,
    listLiaraModelsFromEnv(),
  );

  const proj = await query(`SELECT id FROM projects WHERE id = $1 AND owner_id = $2`, [
    projectId,
    userId,
  ]);
  if (!proj.rows[0]) return NextResponse.json({ error: "not found" }, { status: 404 });

  try {
    const run = await query<{ id: string }>(
      `WITH cancelled_wake AS (
         UPDATE sandbox_wake_requests
         SET status = 'cancelled', finished_at = now()
         WHERE project_id = $1 AND status IN ('queued', 'running')
       ),
       run AS (
         INSERT INTO agent_runs (project_id, user_id, model, status)
         VALUES ($1, $2, $3, 'queued')
         RETURNING id
       ),
       msg AS (
         INSERT INTO messages (project_id, run_id, role, content)
         SELECT $1, run.id, 'user', $4 FROM run
       ),
       touch AS (
         UPDATE sandboxes SET last_active_at = now() WHERE project_id = $1
       )
       SELECT id FROM run`,
      [projectId, userId, model, content],
    );
    const runId = run.rows[0].id;
    return NextResponse.json({ runId });
  } catch (e: unknown) {
    const err = e as { code?: string };
    if (err.code === "23505") {
      const active = await query<{ id: string }>(
        `SELECT id FROM agent_runs WHERE project_id = $1 AND status IN ('queued','running') LIMIT 1`,
        [projectId],
      );
      return NextResponse.json(
        { error: "اجرای دیگری در حال انجام است", runId: active.rows[0]?.id },
        { status: 409 },
      );
    }
    throw e;
  }
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id: projectId } = await params;
  await query(
    `WITH cancelled_run AS (
       UPDATE agent_runs
       SET cancel_requested_at = now(), status = 'cancelled', finished_at = now()
       WHERE project_id = $1 AND user_id = $2 AND status IN ('queued','running')
     )
     UPDATE sandbox_wake_requests
     SET status = 'cancelled', finished_at = now()
     WHERE project_id = $1 AND user_id = $2 AND status IN ('queued','running')`,
    [projectId, userId],
  );
  return NextResponse.json({ ok: true });
}