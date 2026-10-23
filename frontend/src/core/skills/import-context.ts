"use client";

import { useTenantKey } from "@/core/agents/hooks";
import { getAuthToken } from "@/core/auth/auth-api";
import { useSession } from "@/core/auth/hooks";
import { useCurrentTenant } from "@/core/tenants/hooks";
import { getCurrentTenantId } from "@/core/tenants/store";

export function useSkillImportContext() {
  const tenant = useTenantKey();
  const { data: session } = useSession();
  const { data: current } = useCurrentTenant();
  const token = session?.session.token;
  const identityReady =
    !!session?.user.id && !!token && token === getAuthToken();
  const canShare =
    identityReady &&
    current?.tenant_id === tenant &&
    current.role === "tenant_admin";
  const key = JSON.stringify([
    tenant,
    session?.user.id,
    session?.session.id,
    canShare,
    identityReady,
  ]);
  return {
    key,
    identityReady,
    canShare,
    isCurrent: () =>
      identityReady &&
      token === getAuthToken() &&
      tenant === (getCurrentTenantId() ?? "_"),
  };
}
