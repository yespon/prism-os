import fs from "node:fs";
import path from "node:path";

function demoBase(): string | null {
  const base = path.join(
    fs.realpathSync(process.cwd()),
    "public",
    "demo",
    "threads",
  );
  return fs.realpathSync(base) === base ? base : null;
}

/** Only static public demo files; never runtime data, config, or another thread. */
export function readDemoFile(threadId: string, parts: string[]): Buffer | null {
  if (
    !/^[A-Za-z0-9_-]{1,128}$/.test(threadId) ||
    parts.length === 0 ||
    parts.some(
      (part) => !part || part === "." || part === ".." || /[/\\\0]/.test(part),
    )
  )
    return null;
  try {
    const base = demoBase();
    if (base === null) return null;
    const threadRoot = path.join(base, threadId);
    const filename = path.join(threadRoot, ...parts);
    const realThread = fs.realpathSync(threadRoot);
    const realFile = fs.realpathSync(filename);
    if (
      realThread !== threadRoot ||
      !realFile.startsWith(realThread + path.sep) ||
      !fs.statSync(realFile).isFile()
    )
      return null;
    // The fixed demo base bounds tracing even though the selected filename varies.
    return fs.readFileSync(realFile);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT" || code === "ENOTDIR" || code === "ELOOP")
      return null;
    throw error;
  }
}

/** Missing optional demo data produces an empty list in static mode. */
export function listDemoThreads(): string[] {
  try {
    const base = demoBase();
    if (base === null) return [];
    return fs
      .readdirSync(base, {
        withFileTypes: true,
      })
      .filter(
        (entry) =>
          entry.isDirectory() && /^[A-Za-z0-9_-]{1,128}$/.test(entry.name),
      )
      .map((entry) => entry.name);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT" || code === "ENOTDIR") return [];
    throw error;
  }
}
