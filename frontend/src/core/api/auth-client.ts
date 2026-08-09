"use client";

import { getAuthToken } from "@/core/auth/auth-api";
import { getBackendBaseURL } from "@/core/config";
import { getCurrentTenantId } from "@/core/tenants";

/**
 * Fetch wrapper that attaches the Auth session token and base URL
 * to call Gateway APIs.
 */
export async function fetchAuthApi(path: string, options: RequestInit = {}) {
  const headers = await getAuthHeaders(options.headers, path);
  const baseUrl = getBackendBaseURL();

  return fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
}

export async function getAuthHeaders(baseHeaders?: HeadersInit, path?: string) {
  const token = getAuthToken();

  const headers = new Headers(baseHeaders);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (path && (path.includes("/login") || path.includes("/signup"))) {
    return headers;
  }

  const tenantId = getCurrentTenantId();
  if (tenantId) {
    headers.set("X-Tenant-Id", tenantId);
  }

  return headers;
}
