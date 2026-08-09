import { getBackendBaseURL } from "@/core/config";

// Matches the response shape from backend /api/auth/* endpoints.
// Kept compatible with the previous better-auth SessionResponse type.

export interface AuthUser {
  id: string;
  name?: string | null;
  email?: string | null;
  emailVerified: boolean;
  image?: string | null;
  role?: string;
  createdAt?: string;
  updatedAt?: string;
  mustChangePassword?: boolean;
  isBootstrapAdmin?: boolean;
}

export interface AuthSession {
  id?: string;
  token: string;
  expiresAt?: string;
  userId?: string;
  createdAt?: string;
  ipAddress?: string | null;
  userAgent?: string | null;
}

export interface Session {
  session: AuthSession;
  user: AuthUser;
}

const SESSION_COOKIE = "better-auth.session_token";

function readSessionCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = new RegExp(`(?:^|;\\s*)${SESSION_COOKIE}=([^;]*)`).exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

/** Read the session token from the cookie set by the backend. */
export function getAuthToken(): string | null {
  return readSessionCookie();
}

const baseUrl = () => getBackendBaseURL();

export async function login(
  email: string,
  password: string,
): Promise<{ data?: Session; error?: { message: string } }> {
  const res = await fetch(`${baseUrl()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, rememberMe: true }),
    credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    return { error: { message: (detail).detail ?? "Login failed" } };
  }
  const data = (await res.json()) as Session;
  return { data };
}

export async function logout(): Promise<void> {
  await fetch(`${baseUrl()}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function getSession(): Promise<Session | null> {
  const token = readSessionCookie();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${baseUrl()}/api/auth/session`, {
    headers,
    credentials: "include",
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { session?: AuthSession | null; user?: AuthUser | null };
  if (!data.session || !data.user) return null;
  return data as Session;
}

export async function signUp(
  name: string,
  email: string,
  password: string,
): Promise<{ data?: Session; error?: { message: string } }> {
  const res = await fetch(`${baseUrl()}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
    credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    return { error: { message: (detail).detail ?? "Registration failed" } };
  }
  const data = (await res.json()) as Session;
  return { data };
}
