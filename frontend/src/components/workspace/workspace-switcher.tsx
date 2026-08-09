"use client";

import {
  AlertCircleIcon,
  Building2Icon,
  ChevronRightIcon,
  Loader2Icon,
} from "lucide-react";
import Link from "next/link";

import { useI18n } from "@/core/i18n/hooks";
import { useCurrentTenant, useTenantList } from "@/core/tenants";
import { cn } from "@/lib/utils";

type WorkspaceSwitcherProps = {
  compact?: boolean;
  className?: string;
};

export function WorkspaceSwitcher({
  compact = false,
  className,
}: WorkspaceSwitcherProps) {
  const { t } = useI18n();
  const {
    data: currentTenant,
    isLoading: currentLoading,
    error: currentError,
  } = useCurrentTenant();
  const {
    data: tenants,
    isLoading: tenantsLoading,
    error: tenantsError,
  } = useTenantList();

  const isLoading = currentLoading || tenantsLoading;
  const hasError = Boolean(currentError ?? tenantsError);
  const tenantList = tenants ?? [];
  const currentTenantDetail = tenantList.find(
    (tenant) => tenant.id === currentTenant?.tenant_id,
  );
  const canSwitch = tenantList.length > 1;

  if (compact) {
    if (isLoading) {
      return (
        <div
          className={cn(
            "relative flex size-10 items-center justify-center rounded-xl border bg-muted text-muted-foreground",
            className,
          )}
          aria-label={t.workspaceSwitcher.loading}
        >
          <Loader2Icon className="size-4 animate-spin" />
        </div>
      );
    }

    if (hasError) {
      return (
        <Link
          href="/select-workspace"
          className={cn(
            "relative flex size-10 items-center justify-center rounded-xl border border-destructive/30 bg-destructive/10 text-destructive",
            className,
          )}
          title={t.workspaceSwitcher.loadFailed}
          aria-label={t.workspaceSwitcher.loadFailed}
        >
          <AlertCircleIcon className="size-4" />
        </Link>
      );
    }

    if (!currentTenantDetail) {
      return (
        <Link
          href="/select-workspace"
          className={cn(
            "relative flex size-10 items-center justify-center rounded-xl border bg-muted text-muted-foreground",
            className,
          )}
          title={t.workspaceSwitcher.selectWorkspace}
          aria-label={t.workspaceSwitcher.selectWorkspace}
        >
          <Building2Icon className="size-4" />
        </Link>
      );
    }

    return (
      <Link
        href="/select-workspace"
        className={cn(
          "relative flex size-10 items-center justify-center rounded-xl bg-zinc-900 text-white shadow-sm transition hover:opacity-90 dark:bg-white dark:text-zinc-900",
          className,
        )}
        title={
          canSwitch
            ? t.workspaceSwitcher.currentClickToSwitch(currentTenantDetail.name)
            : t.workspaceSwitcher.currentWorkspace(currentTenantDetail.name)
        }
        aria-label={
          canSwitch
            ? t.workspaceSwitcher.currentClickToSwitch(currentTenantDetail.name)
            : t.workspaceSwitcher.currentWorkspace(currentTenantDetail.name)
        }
      >
        <span className="text-sm font-bold uppercase">
          {currentTenantDetail.name.charAt(0)}
        </span>
        {canSwitch ? (
          <span className="absolute -right-1 -bottom-1 rounded-full border bg-background p-0.5 text-foreground">
            <ChevronRightIcon className="size-2.5" />
          </span>
        ) : null}
      </Link>
    );
  }

  if (isLoading) {
    return (
      <div
        className={cn(
          "flex max-w-[320px] items-center gap-3 rounded-full border bg-muted px-3 py-2 text-muted-foreground",
          className,
        )}
      >
        <Loader2Icon className="size-4 animate-spin" />
        <span className="text-sm">{t.workspaceSwitcher.loading}</span>
      </div>
    );
  }

  if (hasError) {
    return (
      <Link
        href="/select-workspace"
        className={cn(
          "flex max-w-[320px] items-center gap-3 rounded-full border border-destructive/30 bg-destructive/10 px-3 py-2 text-destructive transition hover:bg-destructive/15",
          className,
        )}
      >
        <AlertCircleIcon className="size-4 shrink-0" />
        <span className="truncate text-sm font-medium">{t.workspaceSwitcher.loadFailed}</span>
      </Link>
    );
  }

  if (!currentTenantDetail) {
    return (
      <Link
        href="/select-workspace"
        className={cn(
          "flex max-w-[320px] items-center gap-3 rounded-full border bg-background/80 px-3 py-2 transition hover:bg-background",
          className,
        )}
      >
        <Building2Icon className="size-4 shrink-0" />
        <span className="truncate text-sm font-medium">{t.workspaceSwitcher.selectWorkspace}</span>
      </Link>
    );
  }

  if (!canSwitch) {
    return (
      <div
        className={cn(
          "flex max-w-[320px] items-center gap-3 rounded-full border bg-background/80 px-3 py-2",
          className,
        )}
      >
        <div className="bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 flex size-8 shrink-0 items-center justify-center rounded-full">
          <Building2Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{currentTenantDetail.name}</div>
          <div className="text-muted-foreground truncate text-xs">{currentTenantDetail.slug}</div>
        </div>
      </div>
    );
  }

  return (
    <Link
      href="/select-workspace"
      className={cn(
        "bg-background/80 hover:bg-background flex max-w-[320px] items-center gap-3 rounded-full border px-3 py-2 transition-colors",
        className,
      )}
    >
      <div className="bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 flex size-8 shrink-0 items-center justify-center rounded-full">
        <Building2Icon className="size-4" />
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{currentTenantDetail.name}</div>
        <div className="text-muted-foreground flex items-center gap-2 text-xs">
          <span className="truncate">{currentTenantDetail.slug}</span>
          <span>{t.workspaceSwitcher.switchWorkspace}</span>
        </div>
      </div>
      <ChevronRightIcon className="text-muted-foreground size-4 shrink-0" />
    </Link>
  );
}