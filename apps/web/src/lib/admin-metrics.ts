import { query } from "@/lib/db";

async function scalar(text: string, params: unknown[] = []): Promise<number> {
  const res = await query<{ n: number }>(text, params);
  return Number(res.rows[0]?.n ?? 0);
}

export type Funnel = {
  signups: number;
  projects: number;
  userMessages: number;
  agentReplies: number;
  previewUrls: number;
  previewOpens: number;
  previewCopies: number;
  followUps: number;
};

async function funnel(since: Date | null): Promise<Funnel> {
  const sinceIso = since?.toISOString() ?? null;
  const [
    signups,
    projects,
    userMessages,
    agentReplies,
    previewUrls,
    previewOpens,
    previewCopies,
    followUps,
  ] = await Promise.all([
    scalar(
      `SELECT COUNT(*)::int AS n FROM users u
       WHERE u.status <> 'deleted'
         AND ($1::timestamptz IS NULL OR u.created_at >= $1)`,
      [sinceIso],
    ),
    scalar(
      `SELECT COUNT(DISTINCT p.owner_id)::int AS n
       FROM projects p
       JOIN users u ON u.id = p.owner_id
       WHERE u.status <> 'deleted' AND p.status <> 'deleted'
         AND ($1::timestamptz IS NULL OR p.created_at >= $1)`,
      [sinceIso],
    ),
    scalar(
      `SELECT COUNT(DISTINCT p.owner_id)::int AS n
       FROM messages m
       JOIN projects p ON p.id = m.project_id
       JOIN users u ON u.id = p.owner_id
       WHERE m.role = 'user' AND u.status <> 'deleted'
         AND ($1::timestamptz IS NULL OR m.created_at >= $1)`,
      [sinceIso],
    ),
    scalar(
      `SELECT COUNT(DISTINCT p.owner_id)::int AS n
       FROM messages m
       JOIN projects p ON p.id = m.project_id
       JOIN users u ON u.id = p.owner_id
       WHERE m.role = 'assistant' AND u.status <> 'deleted'
         AND ($1::timestamptz IS NULL OR m.created_at >= $1)`,
      [sinceIso],
    ),
    scalar(
      `SELECT COUNT(DISTINCT p.owner_id)::int AS n
       FROM sandboxes s
       JOIN projects p ON p.id = s.project_id
       JOIN users u ON u.id = p.owner_id
       WHERE u.status <> 'deleted'
         AND s.preview_url IS NOT NULL AND s.preview_url <> ''
         AND ($1::timestamptz IS NULL OR s.updated_at >= $1)`,
      [sinceIso],
    ),
    scalar(
      `SELECT COUNT(DISTINCT e.user_id)::int AS n
       FROM product_events e
       JOIN users u ON u.id = e.user_id
       WHERE e.name = 'preview_open' AND u.status <> 'deleted'
         AND ($1::timestamptz IS NULL OR e.created_at >= $1)`,
      [sinceIso],
    ),
    scalar(
      `SELECT COUNT(DISTINCT e.user_id)::int AS n
       FROM product_events e
       JOIN users u ON u.id = e.user_id
       WHERE e.name = 'preview_copy' AND u.status <> 'deleted'
         AND ($1::timestamptz IS NULL OR e.created_at >= $1)`,
      [sinceIso],
    ),
    scalar(
      `SELECT COUNT(*)::int AS n FROM (
         SELECT p.owner_id
         FROM messages m
         JOIN projects p ON p.id = m.project_id
         JOIN users u ON u.id = p.owner_id
         WHERE m.role = 'user' AND u.status <> 'deleted'
         GROUP BY p.owner_id
         HAVING COUNT(*) >= 2
           AND ($1::timestamptz IS NULL OR MAX(m.created_at) >= $1)
       ) s`,
      [sinceIso],
    ),
  ]);
  return {
    signups,
    projects,
    userMessages,
    agentReplies,
    previewUrls,
    previewOpens,
    previewCopies,
    followUps,
  };
}

async function activatedBetween(start: Date, end: Date): Promise<number> {
  return scalar(
    `SELECT COUNT(*)::int AS n
     FROM users u
     WHERE u.status <> 'deleted'
       AND EXISTS (
         SELECT 1 FROM messages m
         JOIN projects p ON p.id = m.project_id
         WHERE p.owner_id = u.id AND m.role = 'assistant'
           AND m.created_at >= $1 AND m.created_at < $2
       )
       AND EXISTS (
         SELECT 1 FROM product_events e
         WHERE e.user_id = u.id
           AND e.name IN ('preview_open', 'preview_copy')
           AND e.created_at >= $1 AND e.created_at < $2
       )`,
    [start.toISOString(), end.toISOString()],
  );
}

export async function loadOverview() {
  const now = new Date();
  const day = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const week = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const prevWeek = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);
  const [allTime, last7, northStar, previousNorthStar, runs, median, activeDay] =
    await Promise.all([
      funnel(null),
      funnel(week),
      activatedBetween(week, now),
      activatedBetween(prevWeek, week),
      query<{ succeeded: number; finished: number }>(
        `SELECT
           COUNT(*) FILTER (WHERE status = 'succeeded')::int AS succeeded,
           COUNT(*) FILTER (WHERE status IN ('succeeded', 'failed', 'cancelled'))::int AS finished
         FROM agent_runs
         WHERE created_at >= $1`,
        [week.toISOString()],
      ),
      query<{ minutes: number | null }>(
        `SELECT percentile_cont(0.5) WITHIN GROUP (
           ORDER BY EXTRACT(EPOCH FROM (first_open - u.created_at)) / 60.0
         ) AS minutes
         FROM users u
         JOIN (
           SELECT user_id, MIN(created_at) AS first_open
           FROM product_events
           WHERE name = 'preview_open'
           GROUP BY user_id
         ) e ON e.user_id = u.id
         WHERE u.status <> 'deleted'`,
      ),
      scalar(
        `SELECT COUNT(DISTINCT user_id)::int AS n FROM (
           SELECT p.owner_id AS user_id
           FROM messages m
           JOIN projects p ON p.id = m.project_id
           WHERE m.created_at >= $1
           UNION
           SELECT user_id FROM product_events WHERE created_at >= $1
         ) s`,
        [day.toISOString()],
      ),
    ]);
  const runRow = runs.rows[0];
  const finished = Number(runRow?.finished ?? 0);
  const succeeded = Number(runRow?.succeeded ?? 0);
  const minutes = median.rows[0]?.minutes;
  return {
    northStar,
    previousNorthStar,
    funnel: { allTime, last7 },
    runSuccess:
      finished === 0
        ? null
        : { succeeded, finished, rate: succeeded / finished },
    medianMinutesToFirstOpen:
      minutes == null || Number.isNaN(Number(minutes)) ? null : Number(minutes),
    activeLastDay: activeDay,
  };
}

export type AdminUserMessage = {
  content: string;
  created_at: string;
  title: string;
};

export type AdminUserRow = {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
  projects: number;
  user_messages: number;
  agent_replies: number;
  preview_opens: number;
  preview_copies: number;
  last_activity: string;
  activated: boolean;
  recent_user_messages: AdminUserMessage[];
  preview_urls: string[];
};

function asMessages(value: unknown): AdminUserMessage[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as { content?: unknown; created_at?: unknown; title?: unknown };
    return [
      {
        content: String(row.content ?? ""),
        created_at: String(row.created_at ?? ""),
        title: String(row.title ?? ""),
      },
    ];
  });
}

function asUrls(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? "")).filter(Boolean);
}

export async function loadAdminUsers(): Promise<AdminUserRow[]> {
  const res = await query<AdminUserRow>(
    `SELECT
       u.id,
       u.email::text AS email,
       u.display_name,
       u.created_at,
       (SELECT COUNT(*)::int FROM projects p
        WHERE p.owner_id = u.id AND p.status <> 'deleted') AS projects,
       (SELECT COUNT(*)::int FROM messages m
        JOIN projects p ON p.id = m.project_id
        WHERE p.owner_id = u.id AND m.role = 'user') AS user_messages,
       (SELECT COUNT(*)::int FROM messages m
        JOIN projects p ON p.id = m.project_id
        WHERE p.owner_id = u.id AND m.role = 'assistant') AS agent_replies,
       (SELECT COUNT(*)::int FROM product_events e
        WHERE e.user_id = u.id AND e.name = 'preview_open') AS preview_opens,
       (SELECT COUNT(*)::int FROM product_events e
        WHERE e.user_id = u.id AND e.name = 'preview_copy') AS preview_copies,
       GREATEST(
         u.created_at,
         COALESCE((SELECT MAX(m.created_at) FROM messages m
                   JOIN projects p ON p.id = m.project_id
                   WHERE p.owner_id = u.id), u.created_at),
         COALESCE((SELECT MAX(e.created_at) FROM product_events e
                   WHERE e.user_id = u.id), u.created_at)
       ) AS last_activity,
       (
         EXISTS (
           SELECT 1 FROM messages m
           JOIN projects p ON p.id = m.project_id
           WHERE p.owner_id = u.id AND m.role = 'assistant'
         )
         AND EXISTS (
           SELECT 1 FROM product_events e
           WHERE e.user_id = u.id AND e.name IN ('preview_open', 'preview_copy')
         )
       ) AS activated,
       (
         SELECT COALESCE(json_agg(json_build_object(
           'content', t.content,
           'created_at', t.created_at,
           'title', t.title
         ) ORDER BY t.created_at DESC), '[]'::json)
         FROM (
           SELECT m.content, m.created_at, p.title
           FROM messages m
           JOIN projects p ON p.id = m.project_id
           WHERE p.owner_id = u.id AND m.role = 'user'
           ORDER BY m.created_at DESC
           LIMIT 8
         ) t
       ) AS recent_user_messages,
       (
         SELECT COALESCE(json_agg(s.preview_url), '[]'::json)
         FROM sandboxes s
         JOIN projects p ON p.id = s.project_id
         WHERE p.owner_id = u.id
           AND p.status <> 'deleted'
           AND COALESCE(s.preview_url, '') <> ''
       ) AS preview_urls
     FROM users u
     WHERE u.status <> 'deleted'
     ORDER BY u.created_at DESC`,
  );
  return res.rows.map((row) => ({
    ...row,
    projects: Number(row.projects),
    user_messages: Number(row.user_messages),
    agent_replies: Number(row.agent_replies),
    preview_opens: Number(row.preview_opens),
    preview_copies: Number(row.preview_copies),
    activated: Boolean(row.activated),
    recent_user_messages: asMessages(row.recent_user_messages),
    preview_urls: asUrls(row.preview_urls),
  }));
}

export async function loadAdminUser(userId: string) {
  const user = await query<{
    id: string;
    email: string;
    display_name: string | null;
    created_at: string;
    status: string;
  }>(
    `SELECT id, email::text AS email, display_name, created_at, status
     FROM users WHERE id = $1 AND status <> 'deleted'`,
    [userId],
  );
  if (!user.rows[0]) return null;
  const [projects, messages] = await Promise.all([
    query<{
      id: string;
      title: string;
      status: string;
      created_at: string;
      preview_url: string | null;
      opens: number;
      copies: number;
    }>(
      `SELECT p.id, p.title, p.status, p.created_at, s.preview_url,
              (SELECT COUNT(*)::int FROM product_events e
               WHERE e.project_id = p.id AND e.name = 'preview_open') AS opens,
              (SELECT COUNT(*)::int FROM product_events e
               WHERE e.project_id = p.id AND e.name = 'preview_copy') AS copies
       FROM projects p
       LEFT JOIN sandboxes s ON s.project_id = p.id
       WHERE p.owner_id = $1 AND p.status <> 'deleted'
       ORDER BY p.updated_at DESC`,
      [userId],
    ),
    query<{
      id: string;
      role: string;
      content: string;
      created_at: string;
      project_id: string;
      title: string;
    }>(
      `SELECT m.id, m.role, m.content, m.created_at, p.id AS project_id, p.title
       FROM messages m
       JOIN projects p ON p.id = m.project_id
       WHERE p.owner_id = $1 AND m.role IN ('user', 'assistant')
       ORDER BY m.created_at DESC
       LIMIT 200`,
      [userId],
    ),
  ]);
  return {
    user: user.rows[0],
    projects: projects.rows.map((p) => ({
      ...p,
      opens: Number(p.opens),
      copies: Number(p.copies),
    })),
    messages: [...messages.rows].reverse(),
  };
}
