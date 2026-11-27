import { query } from "@/lib/db";

/** First pause, then a hard stop. Amounts are Liara toman already stored on usage_ledger. */
export const USAGE_SOFT_TOMAN = 50_000;
export const USAGE_HARD_TOMAN = 70_000;
export const USAGE_COOLDOWN_MS = 60 * 60 * 1000;

export type UsageGate = {
  state: "open" | "cooldown" | "blocked";
  toman: number;
  resumeAt: string | null;
};

export function decideUsageGate(
  totalToman: number,
  softCrossedAt: Date | null,
  now: Date,
): UsageGate {
  const toman = Number.isFinite(totalToman) ? totalToman : 0;
  if (toman >= USAGE_HARD_TOMAN) {
    return { state: "blocked", toman, resumeAt: null };
  }
  if (toman >= USAGE_SOFT_TOMAN && softCrossedAt) {
    const resumeAt = new Date(softCrossedAt.getTime() + USAGE_COOLDOWN_MS);
    if (now < resumeAt) {
      return { state: "cooldown", toman, resumeAt: resumeAt.toISOString() };
    }
  }
  return { state: "open", toman, resumeAt: null };
}

export async function loadUsageGate(userId: string, now = new Date()): Promise<UsageGate> {
  const result = await query<{ total: number; soft_at: Date | string | null }>(
    `WITH ledger AS (
       SELECT id, created_at, cost_toman::float8 AS cost
       FROM usage_ledger
       WHERE user_id = $1
     ),
     running AS (
       SELECT created_at, id,
              SUM(cost) OVER (ORDER BY created_at ASC, id ASC) AS running
       FROM ledger
     )
     SELECT
       COALESCE((SELECT SUM(cost) FROM ledger), 0) AS total,
       (
         SELECT created_at
         FROM running
         WHERE running >= $2
         ORDER BY created_at ASC, id ASC
         LIMIT 1
       ) AS soft_at`,
    [userId, USAGE_SOFT_TOMAN],
  );
  const row = result.rows[0];
  const total = Number(row?.total ?? 0);
  const raw = row?.soft_at;
  const softAt = raw == null ? null : raw instanceof Date ? raw : new Date(raw);
  const crossed = softAt && !Number.isNaN(softAt.getTime()) ? softAt : null;
  return decideUsageGate(total, crossed, now);
}
