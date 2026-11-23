import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export function getPool() {
  return pool;
}

export async function query<T extends Record<string, unknown> = Record<string, unknown>>(
  text: string,
  params?: unknown[],
) {
  const r = await pool.query<T>(text, params);
  return r;
}