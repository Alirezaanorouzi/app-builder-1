import { query } from "@/lib/db";

/** True only when the flag row exists and is enabled. */
export async function flagEnabled(key: string): Promise<boolean> {
  const res = await query<{ enabled: boolean }>(
    `SELECT enabled FROM feature_flags WHERE key = $1`,
    [key],
  );
  return res.rows[0]?.enabled === true;
}
