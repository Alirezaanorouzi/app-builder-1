import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/auth";
import { latestOrDefaultProject } from "@/lib/project-bootstrap";

export async function GET() {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const projectId = await latestOrDefaultProject(userId);
  return NextResponse.json({ projectId });
}