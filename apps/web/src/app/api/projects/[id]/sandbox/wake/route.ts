import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { query } from "@/lib/db";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id: projectId } = await params;

  const proj = await query<{ id: string }>(
    `SELECT id FROM projects WHERE id = $1 AND owner_id = $2`,
    [projectId, userId],
  );
  if (!proj.rows[0]) return NextResponse.json({ error: "not found" }, { status: 404 });

  const active = await query<{ id: string; status: string }>(
    `SELECT id, status FROM sandbox_wake_requests
     WHERE project_id = $1 AND status IN ('queued', 'running')
     ORDER BY created_at DESC LIMIT 1`,
    [projectId],
  );
  if (active.rows[0]) {
    return NextResponse.json({
      wakeId: active.rows[0].id,
      status: active.rows[0].status,
      alreadyQueued: true,
    });
  }

  try {
    const row = await query<{ id: string }>(
      `INSERT INTO sandbox_wake_requests (project_id, user_id, status)
       VALUES ($1, $2, 'queued') RETURNING id`,
      [projectId, userId],
    );
    await query(`UPDATE sandboxes SET last_active_at = now() WHERE project_id = $1`, [
      projectId,
    ]);
    return NextResponse.json({ wakeId: row.rows[0].id, status: "queued" });
  } catch (e: unknown) {
    const err = e as { code?: string };
    if (err.code === "23505") {
      const again = await query<{ id: string; status: string }>(
        `SELECT id, status FROM sandbox_wake_requests
         WHERE project_id = $1 AND status IN ('queued', 'running') LIMIT 1`,
        [projectId],
      );
      return NextResponse.json(
        {
          wakeId: again.rows[0]?.id,
          status: again.rows[0]?.status ?? "queued",
          alreadyQueued: true,
        },
        { status: 202 },
      );
    }
    throw e;
  }
}