import { createRequire } from "node:module";
import process from "node:process";
import { spawnSync } from "node:child_process";

const require = createRequire(import.meta.url);
const next = require.resolve("next/dist/bin/next");
const tsc = require.resolve("typescript/bin/tsc");
const requestedArgs = process.argv.slice(2);
const buildArgs = requestedArgs.some((arg) => ["--webpack", "--turbopack", "--turbo"].includes(arg))
  ? requestedArgs
  : ["--webpack", ...requestedArgs];

// Complete strict checks before retaining the production compiler graph.
// Generate current route contracts so new handlers are checked as well.
for (const [args, checked] of [
  [[next, "typegen"], false],
  [[tsc, "--noEmit"], false],
  [[next, "build", ...buildArgs], true],
]) {
  if (args[0] === tsc) {
    process.stdout.write("Checking TypeScript and generated route contracts...\n");
  }
  if (checked) {
    process.stdout.write("Strict typecheck passed; starting production compiler...\n");
  }
  const result = spawnSync(process.execPath, args, {
    stdio: "inherit",
    env: {
      ...process.env,
      PRISMOS_PREBUILD_TYPECHECK_DONE: checked ? "1" : "",
    },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
