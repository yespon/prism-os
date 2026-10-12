/**
 * Run `build` or `dev` with `SKIP_ENV_VALIDATION` to skip env validation. This is especially useful
 * for Docker builds.
 */
import "./src/env.js";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

/** @type {import("next").NextConfig} */
const config = {
  devIndicators: false,
  // scripts/build.mjs checks freshly generated routes before compilation.
  // Direct Next invocations retain the built-in typecheck by default.
  typescript: {
    ignoreBuildErrors: process.env.PRISMOS_PREBUILD_TYPECHECK_DONE === "1",
  },
  experimental: { cpus: 2 },
  turbopack: { root: frontendRoot },
  outputFileTracingRoot: frontendRoot,
};

export default config;
