import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { query } from "@/lib/db";

export async function GET() {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const res = await query<{ email: string | null; display_name: string | null; phone: string | null }>(
    `SELECT email::text AS email, display_name, phone
     FROM users WHERE id = $1 AND status = 'active'`,
    [userId],
  );
  const user = res.rows[0];
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  return NextResponse.json({
    email: user.email,
    displayName: user.display_name,
    phone: user.phone,
  });
}
