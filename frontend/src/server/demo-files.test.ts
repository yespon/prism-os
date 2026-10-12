// @vitest-environment node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { listDemoThreads, readDemoFile } from "./demo-files";
import { NextRequest } from "next/server";
import { GET as artifactGET } from "../app/mock/api/threads/[thread_id]/artifacts/[[...artifact_path]]/route";
import { POST as historyPOST } from "../app/mock/api/threads/[thread_id]/history/route";
import { POST as searchPOST } from "../app/mock/api/threads/search/route";

let directory: string;
beforeEach(() => {
  directory = fs.mkdtempSync(path.join(os.tmpdir(), "prismos-demo-"));
  vi.spyOn(process, "cwd").mockReturnValue(directory);
  fs.mkdirSync(path.join(directory, "public/demo/threads/thread-a/outputs"), {
    recursive: true,
  });
  fs.writeFileSync(
    path.join(directory, "public/demo/threads/thread-a/outputs/report.txt"),
    "public demo",
  );
  fs.writeFileSync(path.join(directory, "private.txt"), "private data");
});
afterEach(() => {
  vi.restoreAllMocks();
  fs.rmSync(directory, { recursive: true, force: true });
});
it("loads existing public demo data and treats missing demos as absent", () => {
  expect(readDemoFile("thread-a", ["outputs", "report.txt"])?.toString()).toBe(
    "public demo",
  );
  expect(readDemoFile("thread-a", ["missing"])).toBeNull();
  expect(readDemoFile("missing", ["outputs", "report.txt"])).toBeNull();
});
it.each([
  ["../thread-a", ["outputs", "report.txt"]],
  ["thread-a", ["..", "private.txt"]],
  ["thread-a", ["outputs/../report.txt"]],
  ["thread-a", ["outputs\\report.txt"]],
  ["thread-a", ["bad\0file"]],
  ["thread-a", []],
] as [string, string[]][])(
  "rejects traversal or invalid segments %s %j",
  (thread, parts) => {
    expect(readDemoFile(thread, parts)).toBeNull();
  },
);
it("rejects file and thread symlinks that escape the demo boundary", () => {
  fs.symlinkSync(
    path.join(directory, "private.txt"),
    path.join(directory, "public/demo/threads/thread-a/outputs/link"),
  );
  fs.symlinkSync(
    directory,
    path.join(directory, "public/demo/threads/linked-thread"),
  );
  expect(readDemoFile("thread-a", ["outputs", "link"])).toBeNull();
  expect(readDemoFile("linked-thread", ["private.txt"])).toBeNull();
});
it("rejects directories and cross-thread links", () => {
  fs.mkdirSync(path.join(directory, "public/demo/threads/thread-b"));
  fs.writeFileSync(
    path.join(directory, "public/demo/threads/thread-b/report.txt"),
    "different demo",
  );
  fs.symlinkSync(
    path.join(directory, "public/demo/threads/thread-b/report.txt"),
    path.join(directory, "public/demo/threads/thread-a/outputs/other-thread"),
  );
  expect(readDemoFile("thread-a", ["outputs"])).toBeNull();
  expect(readDemoFile("thread-a", ["outputs", "other-thread"])).toBeNull();
});

it("lists valid directories and tolerates an absent optional demo tree", () => {
  fs.mkdirSync(path.join(directory, "public/demo/threads/.hidden"));
  fs.writeFileSync(
    path.join(directory, "public/demo/threads/plain-file"),
    "not a thread",
  );
  expect(listDemoThreads()).toEqual(["thread-a"]);
  fs.renameSync(
    path.join(directory, "public/demo/threads"),
    path.join(directory, "removed-demo"),
  );
  expect(listDemoThreads()).toEqual([]);
});

it("preserves artifact URLs, download headers and mp4 MIME while rejecting traversal", async () => {
  const params = Promise.resolve({
    thread_id: "thread-a",
    artifact_path: ["mnt", "outputs", "report.txt"],
  });
  const response = await artifactGET(
    new NextRequest("http://localhost/mock?download=true"),
    { params },
  );
  expect(response.status).toBe(200);
  expect(await response.text()).toBe("public demo");
  expect(response.headers.get("content-disposition")).toContain("report.txt");
  fs.writeFileSync(
    path.join(directory, "public/demo/threads/thread-a/outputs/video.mp4"),
    "video",
  );
  const video = await artifactGET(new NextRequest("http://localhost/mock"), {
    params: Promise.resolve({
      thread_id: "thread-a",
      artifact_path: ["mnt", "outputs", "video.mp4"],
    }),
  });
  expect(video.headers.get("content-type")).toBe("video/mp4");
  for (const artifact_path of [
    ["outputs", "report.txt"],
    ["mnt", "..", "private.txt"],
    ["mnt", "missing"],
  ]) {
    const result = await artifactGET(new NextRequest("http://localhost/mock"), {
      params: Promise.resolve({ thread_id: "thread-a", artifact_path }),
    });
    expect(result.status).toBe(404);
  }
});
it("preserves both history shapes and returns 404 for missing demos", async () => {
  const request = new NextRequest("http://localhost/mock", { method: "POST" });
  const params = Promise.resolve({ thread_id: "thread-a" });
  const file = path.join(directory, "public/demo/threads/thread-a/thread.json");
  fs.writeFileSync(file, JSON.stringify({ values: { messages: [] } }));
  expect(await (await historyPOST(request, { params })).json()).toEqual([
    { values: { messages: [] } },
  ]);
  fs.writeFileSync(file, JSON.stringify({ history: [{ values: {} }] }));
  expect(await (await historyPOST(request, { params })).json()).toEqual({
    history: [{ values: {} }],
  });
  expect(
    (
      await historyPOST(request, {
        params: Promise.resolve({ thread_id: "missing" }),
      })
    ).status,
  ).toBe(404);
});
it("searches sorted and paged demos without following unrelated directories", async () => {
  fs.writeFileSync(
    path.join(directory, "public/demo/threads/thread-a/thread.json"),
    JSON.stringify({ created_at: "2026-01-01T00:00:00Z" }),
  );
  fs.mkdirSync(path.join(directory, "public/demo/threads/thread-b"));
  fs.writeFileSync(
    path.join(directory, "public/demo/threads/thread-b/thread.json"),
    JSON.stringify({ updated_at: "2026-02-01T00:00:00Z" }),
  );
  fs.symlinkSync(directory, path.join(directory, "public/demo/threads/linked"));
  const response = await searchPOST(
    new Request("http://localhost/mock", {
      method: "POST",
      body: JSON.stringify({ limit: 1, offset: 1 }),
    }),
  );
  const results = await response.json();
  expect(results).toHaveLength(1);
  expect(results[0].thread_id).toBe("thread-a");
  expect(results[0].updated_at).toBe("2026-01-01T00:00:00Z");
  fs.renameSync(
    path.join(directory, "public/demo/threads"),
    path.join(directory, "removed-demo"),
  );
  expect(
    await (
      await searchPOST(
        new Request("http://localhost/mock", { method: "POST", body: "{}" }),
      )
    ).json(),
  ).toEqual([]);
});

it("rejects a demo root symlink and an alias of another thread", () => {
  const base = path.join(directory, "public/demo/threads");
  fs.symlinkSync(path.join(base, "thread-a"), path.join(base, "thread-alias"));
  expect(readDemoFile("thread-alias", ["outputs", "report.txt"])).toBeNull();
  const otherBase = path.join(directory, "private-demo");
  fs.renameSync(base, otherBase);
  fs.symlinkSync(otherBase, base);
  expect(readDemoFile("thread-a", ["outputs", "report.txt"])).toBeNull();
  expect(listDemoThreads()).toEqual([]);
});
