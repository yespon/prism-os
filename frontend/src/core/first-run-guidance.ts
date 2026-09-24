import { env } from "@/env";

/** UI-only rollout switch. Authorization still happens on the server. */
export function isFirstRunGuidanceEnabled(tenantId: string | null | undefined): boolean {
  if (!tenantId) return false;
  return (env.NEXT_PUBLIC_FIRST_RUN_TENANT_IDS ?? "")
    .split(",")
    .some((configuredId) => configuredId.trim() === tenantId);
}
