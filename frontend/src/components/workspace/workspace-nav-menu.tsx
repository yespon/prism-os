"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ShieldAlertIcon,
  Building2Icon,
  ArrowLeftRightIcon,
  CheckIcon,
  ChevronUpIcon,
  GlobeIcon,
  KeyRoundIcon,
  LogOutIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  Settings2Icon,
  UserCircleIcon,
  UserIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChangePasswordDialog } from "@/components/backoffice/change-password-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSidebar } from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { SettingsDialog } from "@/components/workspace/settings";
import { logout } from "@/core/auth/auth-api";
import { useSession } from "@/core/auth/hooks";
import { enUS, zhCN, ja, ko, type Locale } from "@/core/i18n";
import { useI18n } from "@/core/i18n/hooks";
import { canAccessAdminPage } from "@/core/permissions/roles";
import { clearTenantId, useCurrentTenant, useTenantList } from "@/core/tenants";
import { cn } from "@/lib/utils";

export function WorkspaceNavMenu() {
  const { data: session } = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [changePasswordOpen, setChangePasswordOpen] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const { state, toggleSidebar } = useSidebar();
  const isCollapsed = state === "collapsed";

  const { t, locale, changeLocale } = useI18n();

  const isPlatformAdmin = canAccessAdminPage(session?.user?.role);
  const userName = session?.user?.name ?? t.navMenu.user;
  const userEmail = session?.user?.email ?? "";

  const { data: currentTenant } = useCurrentTenant();
  const { data: tenants } = useTenantList();
  const currentTenantDetail = tenants?.find(
    (tenant) => tenant.id === currentTenant?.tenant_id
  );
  const tenantName = currentTenantDetail?.name ?? currentTenant?.tenant_id ?? t.navMenu.unbound;
  const tenantType = currentTenant?.tenant_type ?? currentTenantDetail?.tenant_type ?? "general";
  const canSwitchTenant = (tenants?.length ?? 0) > 1;
  const canAccessTenantAdmin = currentTenant?.role === "tenant_admin";

  const typeLabelMap: Record<string, string> = {
    ops: t.admin.tenants.types.ops,
    product: t.admin.tenants.types.product,
    rd: t.admin.tenants.types.rd,
    general: t.admin.tenants.types.general,
  };
  const typeLabel = typeLabelMap[tenantType] ?? tenantType;

  const languageOptions: { value: Locale; label: string }[] = [
    { value: "en-US", label: enUS.locale.localName },
    { value: "zh-CN", label: zhCN.locale.localName },
    { value: "ja", label: ja.locale.localName },
    { value: "ko", label: ko.locale.localName },
  ];

  const handleSignOut = async () => {
    setIsSigningOut(true);
    try {
      await logout();
      clearTenantId();
      await queryClient.cancelQueries();
      queryClient.clear();
      router.replace("/sign-in");
      router.refresh();
      window.location.assign("/sign-in");
    } catch (error) {
      console.error("退出失败:", error);
    } finally {
      setIsSigningOut(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-3 px-2">
      {/* 平台治理入口 - 仅平台管理员可见 */}
      {isPlatformAdmin && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href="/admin"
              className="flex items-center justify-center rounded-xl text-muted-foreground transition-colors duration-200 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-50 group-data-[collapsible=icon]:size-10 group-data-[collapsible=icon]:w-auto"
              aria-label={t.navMenu.platformGovernance}
            >
              <ShieldAlertIcon className="size-5" strokeWidth={2} />
              <span className="ml-2 text-sm truncate group-data-[collapsible=icon]:hidden">{t.navMenu.platformGovernance}</span>
            </Link>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            {t.navMenu.platformGovernance}
          </TooltipContent>
        </Tooltip>
      )}

      {/* 底部操作区 - 用户菜单 + 设置按钮 */}
      <div className="border-t border-sidebar-border pt-3 mt-1">
        <div className="flex items-center gap-2">
          {/* 用户下拉菜单 - 黑白灰风格 - 收缩时隐藏 */}
          {!isCollapsed && (
            <div className="flex-1 min-w-0">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="group flex h-11 w-full items-center gap-3 rounded-lg px-2 transition-all hover:bg-sidebar-accent">
                    {/* 头像 - 黑白灰 */}
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-zinc-100 transition-transform group-hover:scale-105">
                      <UserIcon className="size-4" />
                    </div>
                    {/* 用户信息 */}
                    <div className="flex-1 min-w-0 text-left">
                      <p className="text-sm font-medium text-sidebar-foreground truncate leading-tight">
                        {userName}
                      </p>
                      <p className="text-[11px] text-sidebar-foreground/50 truncate">
                        {tenantName}
                      </p>
                    </div>
                    {/* 展开指示器 */}
                    <ChevronUpIcon className="size-4 text-sidebar-foreground/40 transition-transform duration-200 group-data-[state=open]:rotate-180" />
                  </button>
                </DropdownMenuTrigger>

                <DropdownMenuContent
                  side="top"
                  align="start"
                  className="w-[200px] bg-sidebar border-sidebar-border shadow-lg"
                  sideOffset={6}
                >
                  {/* 用户信息卡片 - 黑白灰 */}
                  <div className="rounded-md bg-zinc-100 dark:bg-zinc-800 p-3 mb-1">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-800 dark:bg-zinc-700 text-zinc-100">
                        <UserCircleIcon className="size-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-sidebar-foreground truncate">{userName}</p>
                        <p className="text-xs text-sidebar-foreground/60 truncate">{userEmail || "user"}</p>
                      </div>
                    </div>
                    {/* 当前工作空间信息 */}
                    <div className="mt-2 pt-2 border-t border-zinc-200 dark:border-zinc-700">
                      <div className="flex items-center gap-2 text-xs text-sidebar-foreground/70">
                        <Building2Icon className="size-3" />
                        <span className="truncate">{tenantName}</span>
                        <span className="shrink-0 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                          {typeLabel}
                        </span>
                      </div>
                    </div>
                  </div>

                  <DropdownMenuSeparator className="bg-sidebar-border" />

                  {/* 切换工作空间 */}
                  {canSwitchTenant && (
                    <DropdownMenuItem
                      onClick={() => router.push("/select-workspace")}
                      className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm cursor-pointer text-sidebar-foreground/80 hover:text-sidebar-foreground focus:bg-sidebar-accent"
                    >
                      <ArrowLeftRightIcon className="size-4 text-zinc-500 shrink-0" />
                      <span className="truncate">{t.navMenu.switchTenant}</span>
                    </DropdownMenuItem>
                  )}

                  {canAccessTenantAdmin && (
                    <DropdownMenuItem asChild>
                      <Link
                        href="/tenant-admin"
                        className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm cursor-pointer text-sidebar-foreground/80 hover:text-sidebar-foreground focus:bg-sidebar-accent"
                      >
                        <Building2Icon className="size-4 text-zinc-500 shrink-0" />
                        <span className="truncate">{t.navMenu.manageWorkspace}</span>
                      </Link>
                    </DropdownMenuItem>
                  )}

                  {/* 个人设置 */}
                  <DropdownMenuItem
                    onClick={() => setSettingsOpen(true)}
                    className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm cursor-pointer text-sidebar-foreground/80 hover:text-sidebar-foreground focus:bg-sidebar-accent"
                  >
                    <Settings2Icon className="size-4 text-zinc-500 shrink-0" />
                    <span className="truncate">{t.navMenu.personalSettings}</span>
                  </DropdownMenuItem>

                  {/* 修改密码 */}
                  <DropdownMenuItem
                    onClick={() => setChangePasswordOpen(true)}
                    className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm cursor-pointer text-sidebar-foreground/80 hover:text-sidebar-foreground focus:bg-sidebar-accent"
                  >
                    <KeyRoundIcon className="size-4 text-zinc-500 shrink-0" />
                    <span className="truncate">{t.navMenu.changePassword}</span>
                  </DropdownMenuItem>

                  <DropdownMenuSeparator className="bg-sidebar-border" />

                  {/* 语言切换 - 二级菜单 */}
                  <DropdownMenuSub>
                    <DropdownMenuSubTrigger className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm cursor-pointer text-sidebar-foreground/80 hover:text-sidebar-foreground focus:bg-sidebar-accent">
                      <GlobeIcon className="size-4 text-zinc-500 shrink-0" />
                      <span className="truncate">{t.navMenu.language}</span>
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent className="min-w-[140px]">
                      {languageOptions.map((item) => (
                        <DropdownMenuItem
                          key={item.value}
                          onClick={() => changeLocale(item.value)}
                          className="flex items-center gap-2 rounded-md px-2.5 py-2 text-sm cursor-pointer"
                        >
                          <span className="flex-1">{item.label}</span>
                          {locale === item.value && (
                            <CheckIcon className="size-4 text-primary" />
                          )}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>

                  <DropdownMenuSeparator className="bg-sidebar-border" />

                  {/* 退出登录 */}
                  <DropdownMenuItem
                    onClick={handleSignOut}
                    disabled={isSigningOut}
                    className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm cursor-pointer text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 focus:bg-zinc-100 dark:focus:bg-zinc-800"
                  >
                    <LogOutIcon className="size-4" />
                    <span className="truncate">{isSigningOut ? t.navMenu.signingOut : t.navMenu.signOut}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}

          {/* 侧边栏收缩/展开按钮 - 背景色与侧边栏底色一致 */}
          <button
            type="button"
            onClick={toggleSidebar}
            className={cn(
              "flex h-11 shrink-0 items-center justify-center rounded-lg text-sidebar-foreground/70 transition-all hover:bg-sidebar-accent hover:text-sidebar-foreground",
              isCollapsed ? "w-full" : "w-11"
            )}
            title={isCollapsed ? t.navMenu.expandSidebar : t.navMenu.collapseSidebar}
            aria-label={isCollapsed ? t.navMenu.expandSidebar : t.navMenu.collapseSidebar}
          >
            {isCollapsed ? (
              <PanelLeftOpenIcon className="size-5" />
            ) : (
              <PanelLeftCloseIcon className="size-5" />
            )}
          </button>
        </div>
      </div>

      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        defaultSection="appearance"
      />

      <ChangePasswordDialog
        open={changePasswordOpen}
        onOpenChange={setChangePasswordOpen}
      />
    </div>
  );
}
