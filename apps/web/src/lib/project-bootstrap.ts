import { query } from "@/lib/db";

const DEFAULT_TITLE = "پروژه جدید";

async function insertProject(userId: string, title: string) {
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
  return projectId;
}

/** New account: always start in a fresh default project. */
export async function projectAfterSignup(userId: string) {
  return insertProject(userId, DEFAULT_TITLE);
}

/** Returning user: latest project, or a default one if they have none. */
export async function projectAfterLogin(userId: string) {
  const res = await query<{ id: string }>(
    `SELECT id FROM projects
     WHERE owner_id = $1 AND status <> 'deleted'
     ORDER BY updated_at DESC
     LIMIT 1`,
    [userId],
  );
  if (res.rows[0]?.id) return res.rows[0].id;
  return insertProject(userId, DEFAULT_TITLE);
}

export async function latestOrDefaultProject(userId: string) {
  return projectAfterLogin(userId);
}