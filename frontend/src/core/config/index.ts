import { env } from "@/env";

export function getBackendBaseURL() {
  if (env.NEXT_PUBLIC_BACKEND_BASE_URL) {
    return env.NEXT_PUBLIC_BACKEND_BASE_URL;
  }

  // Browser requests must follow the public origin. This keeps the client
  // working when the reverse proxy is exposed on a non-default port and
  // avoids baking an internal Docker hostname or stale development port into
  // the production bundle.
  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  return "";
}

export function getLangGraphBaseURL(isMock?: boolean) {
  if (env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
    return env.NEXT_PUBLIC_LANGGRAPH_BASE_URL;
  } else if (isMock) {
    if (typeof window !== "undefined") {
      return `${window.location.origin}/mock/api`;
    }
    return "http://localhost:3000/mock/api";
  } else {
    // LangGraph SDK requires a full URL, construct it from current origin
    if (typeof window !== "undefined") {
      return `${window.location.origin}/api/langgraph`;
    }
    // Fallback for SSR
    return "http://localhost:2026/api/langgraph";
  }
}

export function getPublicAppURL() {
  if (env.NEXT_PUBLIC_PUBLIC_APP_URL) {
    return env.NEXT_PUBLIC_PUBLIC_APP_URL.replace(/\/$/, "");
  }

  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  return "";
}
