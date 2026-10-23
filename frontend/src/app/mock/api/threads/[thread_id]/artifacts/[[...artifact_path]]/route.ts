import type { NextRequest } from "next/server";

import { readDemoFile } from "@/server/demo-files";

export async function GET(
  request: NextRequest,
  {
    params,
  }: { params: Promise<{ thread_id: string; artifact_path?: string[] }> },
) {
  const { thread_id: threadId, artifact_path: parts = [] } = await params;
  if (parts[0] !== "mnt")
    return new Response("File not found", { status: 404 });
  const data = readDemoFile(threadId, parts.slice(1));
  if (data === null) return new Response("File not found", { status: 404 });
  const headers = new Headers();
  const filename = parts.at(-1) ?? "artifact";
  if (request.nextUrl.searchParams.get("download") === "true")
    headers.set(
      "Content-Disposition",
      `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
    );
  if (filename.endsWith(".mp4")) headers.set("Content-Type", "video/mp4");
  return new Response(new Uint8Array(data), { status: 200, headers });
}
