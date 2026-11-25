import { getSessionUserId } from "@/lib/auth";
import { loadProjectStreamSnapshot } from "@/lib/project-stream-snapshot";
import { NextResponse } from "next/server";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id: projectId } = await params;

  const update = await loadProjectStreamSnapshot(projectId, userId);
  if (!update) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(update);
}