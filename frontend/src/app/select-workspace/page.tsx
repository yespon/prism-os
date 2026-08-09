"use client";

import { Building2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AuthLocaleSwitcher } from "@/components/auth/locale-switcher";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useI18n } from "@/core/i18n/hooks";
import { useTenantList, useSwitchTenant } from "@/core/tenants/hooks";

export default function SelectWorkspacePage() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: tenants, isLoading, error } = useTenantList();
  const switchTenantMutation = useSwitchTenant();
  const [switchingTo, setSwitchingTo] = useState<string | null>(null);

  const nextPath = searchParams.get("next") ?? "/workspace";

  const handleSelect = useCallback(
    async (tenantId: string) => {
      try {
        setSwitchingTo(tenantId);
        await switchTenantMutation.mutateAsync(tenantId);
        router.push(nextPath);
        router.refresh();
      } catch (err) {
        console.error("Failed to switch workspace", err);
        setSwitchingTo(null);
      }
    },
    [nextPath, router, switchTenantMutation],
  );

  useEffect(() => {
    // If only one tenant, auto-switch and redirect
    const firstTenant = tenants?.[0];
    if (tenants?.length === 1 && firstTenant) {
      void handleSelect(firstTenant.id);
    }
  }, [handleSelect, tenants]);

  return (
    <main className="bg-background relative flex min-h-screen items-center justify-center px-4">
      <div className="absolute top-4 right-4">
        <AuthLocaleSwitcher />
      </div>
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t.auth.selectWorkspace.title}</CardTitle>
          <CardDescription>
            {t.auth.selectWorkspace.description}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center p-8">{t.auth.selectWorkspace.loading}</div>
          ) : error ? (
            <div className="text-destructive text-sm text-center">
              {t.auth.selectWorkspace.loadFailed}
            </div>
          ) : tenants && tenants.length > 0 ? (
            <div className="space-y-4">
              {tenants.map((tenant) => (
                <Button
                  key={tenant.id}
                  variant="outline"
                  className="w-full justify-start h-16 px-4"
                  onClick={() => handleSelect(tenant.id)}
                  disabled={switchingTo !== null}
                >
                  <Building2 className="mr-4 h-6 w-6 text-muted-foreground" />
                  <div className="flex flex-col items-start gap-1 flex-1 min-w-0">
                    <span className="font-medium text-base truncate">{tenant.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {tenant.slug}
                    </span>
                  </div>
                  {tenant.tenant_type && (
                    <span className="ml-2 shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                      {t.admin.tenants.types[tenant.tenant_type as keyof typeof t.admin.tenants.types] ?? tenant.tenant_type}
                    </span>
                  )}
                  {switchingTo === tenant.id && (
                    <span className="ml-auto text-sm text-muted-foreground">
                      {t.auth.selectWorkspace.entering}
                    </span>
                  )}
                </Button>
              ))}
            </div>
          ) : (
            <div className="text-center text-sm text-muted-foreground">
              {t.auth.selectWorkspace.noWorkspaces}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
