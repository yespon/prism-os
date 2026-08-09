import { cookies } from "next/headers";
import { cache } from "react";

import type { Session } from "@/core/auth/auth-api";
import { getBackendBaseURL } from "@/core/config";

const SESSION_COOKIE = "better-auth.session_token";

/**
 * Resolve the backend base URL for server-side fetch calls.
 *
 * In Docker, NEXT_PUBLIC_* vars are inlined at build time, so runtime env
 * vars won't take effect.  We use SERVER_BACKEND_URL (no NEXT_PUBLIC_ prefix)
 * as the server-side override — it's read from process.env at runtime and is
 * never inlined.
 */
function resolveServerBackendURL(): string {
  // Server-only env var, set in docker-compose for Docker deployments
  if (typeof process !== "undefined" && process.env.SERVER_BACKEND_URL) {
    return process.env.SERVER_BACKEND_URL;
  }
  return getBackendBaseURL();
}

export const getSession = cache(async (): Promise<Session | null> => {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  try {
    const baseUrl = resolveServerBackendURL();
    const res = await fetch(`${baseUrl}/api/auth/session`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { session?: unknown; user?: unknown };
    if (!data.session || !data.user) return null;
    return data as Session;
  } catch {
    return null;
  }
});

interface BootstrapStatus {
  needs_setup: boolean;
}

export const getBootstrapStatus = cache(async (): Promise<BootstrapStatus> => {
  try {
    const baseUrl = resolveServerBackendURL();
    const res = await fetch(`${baseUrl}/api/auth/bootstrap-status`, {
      cache: "no-store",
    });
    if (!res.ok) return { needs_setup: false };
    return (await res.json()) as BootstrapStatus;
  } catch {
    return { needs_setup: false };
  }
});
