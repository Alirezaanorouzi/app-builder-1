import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { loadUsageGate } from "@/lib/usage-limit";

export async function GET() {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const gate = await loadUsageGate(userId);
  return NextResponse.json(gate);
}
