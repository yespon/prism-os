"use client";

import { useQueryClient } from "@tanstack/react-query";
import { UserIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Item, ItemContent, ItemDescription, ItemTitle } from "@/components/ui/item";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { logout } from "@/core/auth/auth-api";
import { useSession } from "@/core/auth/hooks";
import { useI18n } from "@/core/i18n/hooks";
import { clearTenantId, useCurrentTenant, useSwitchTenant, useTenantList } from "@/core/tenants";

import { SettingsSection } from "./settings-section";

export function UserSettingsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const { data: sessionData, isLoading } = useSession();
  const { data: tenants, isLoading: tenantsLoading } = useTenantList();
  const { data: currentTenant } = useCurrentTenant();
  const switchTenantMutation = useSwitchTenant();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const [tenantError, setTenantError] = useState<string | null>(null);

  const handleSignOut = async () => {
    setIsSigningOut(true);
    setSignOutError(null);

    try {
      await logout();
      clearTenantId();
      await queryClient.cancelQueries();
      queryClient.clear();
      router.replace("/sign-in");
      router.refresh();
      window.location.assign("/sign-in");
    } catch {
      setSignOutError(t.settings.user.signOutFailed);
    } finally {
      setIsSigningOut(false);
    }
  };

  const handleTenantSwitch = async (tenantId: string) => {
    setTenantError(null);
    try {
      await switchTenantMutation.mutateAsync(tenantId);
      router.refresh();
    } catch (error) {
      setTenantError(error instanceof Error ? error.message : "Failed to switch tenant");
    }
  };

  const user = sessionData?.user;

  return (
    <SettingsSection
      title={t.settings.user.title}
      description={t.settings.user.description}
    >
      {isLoading ? (
        <div className="text-muted-foreground text-sm">{t.common.loading}</div>
      ) : (
        <div className="space-y-6">
          {user && (
            <div className="flex items-center gap-4 bg-zinc-50 dark:bg-zinc-900/50 p-4 rounded-xl border border-zinc-200 dark:border-zinc-800">
              <div className="flex items-center justify-center size-12 rounded-full bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">
                <UserIcon className="size-6" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="font-medium text-zinc-900 dark:text-zinc-100 truncate">
                    {user.name ?? user.email ?? user.id}
                  </h3>
                  {user.role === "admin" && (
                    <span className="px-2 py-0.5 text-[10px] font-medium bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400 rounded-full">
                      Admin
                    </span>
                  )}
                </div>
                {user.email && (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 truncate">
                    {user.email}
                  </p>
                )}
                {user.name && user.email && user.name !== user.email && (
                   <p className="text-xs text-zinc-400 dark:text-zinc-500 truncate mt-0.5">
                     ID: {user.id}
                   </p>
                )}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0"
                onClick={() => void handleSignOut()}
                disabled={isSigningOut}
              >
                {isSigningOut
                  ? t.settings.user.signingOut
                  : t.settings.user.signOut}
              </Button>
            </div>
          )}

          {tenants && tenants.length > 0 && (
            <Item variant="outline" className="w-full">
              <ItemContent>
                <ItemTitle>{t.settings.user.currentWorkspace}</ItemTitle>
                <ItemDescription>
                  {t.settings.user.switchWorkspaceHint}
                </ItemDescription>
              </ItemContent>
              <div className="w-full max-w-xs space-y-2">
                <Select
                  value={currentTenant?.tenant_id ?? ""}
                  onValueChange={(tenantId) => {
                    void handleTenantSwitch(tenantId);
                  }}
                  disabled={tenantsLoading || switchTenantMutation.isPending}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t.settings.user.selectWorkspacePlaceholder} />
                  </SelectTrigger>
                  <SelectContent>
                    {tenants.map((tenant) => (
                      <SelectItem key={tenant.id} value={tenant.id}>
                        {tenant.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {tenantError && (
                  <p className="text-destructive text-sm">{tenantError}</p>
                )}
              </div>
            </Item>
          )}

          {!user && (
            <div className="space-y-2 pt-2">
              <Button
                variant="destructive"
                onClick={() => void handleSignOut()}
                disabled={isSigningOut}
              >
                {isSigningOut
                  ? t.settings.user.signingOut
                  : t.settings.user.signOut}
              </Button>
              {signOutError && (
                <p className="text-destructive text-sm">{signOutError}</p>
              )}
            </div>
          )}
        </div>
      )}
    </SettingsSection>
  );
}
