import type { NextRequest } from "next/server";
import { readDemoFile } from "@/server/demo-files";

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ thread_id: string }> },
) {
  const { thread_id: threadId } = await params;
  const data = readDemoFile(threadId, ["thread.json"]);
  if (data === null)
    return Response.json({ detail: "Thread not found" }, { status: 404 });
  const json = JSON.parse(data.toString("utf8"));
  return Response.json(Array.isArray(json.history) ? json : [json]);
}
