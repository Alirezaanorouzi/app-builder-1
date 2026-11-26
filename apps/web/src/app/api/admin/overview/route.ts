import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/auth";
import { loadOverview } from "@/lib/admin-metrics";

export async function GET() {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "not found" }, { status: 404 });
  const overview = await loadOverview();
  return NextResponse.json(overview);
}
