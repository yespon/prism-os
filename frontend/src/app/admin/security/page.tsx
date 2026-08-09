"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { KeyIcon, ShieldCheckIcon, AlertTriangleIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { fetchAuthApi } from "@/core/api/auth-client";
import { logout } from "@/core/auth/auth-api";
import { useSession } from "@/core/auth/hooks";
import { useI18n } from "@/core/i18n/hooks";
import { canAccessAdminPage } from "@/core/permissions/roles";
import { clearTenantId } from "@/core/tenants";

interface BootstrapStatusResponse {
  is_bootstrap_admin: boolean;
  must_change_password: boolean;
}

function fetchBootstrapStatus(): Promise<BootstrapStatusResponse> {
  return fetchAuthApi("/api/admin/bootstrap-status").then((res) => {
    if (!res.ok) throw new Error("Failed to fetch bootstrap status");
    return res.json();
  });
}

export default function SecurityPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  const canAccess = canAccessAdminPage(session?.user?.role);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const { data: statusData, isLoading } = useQuery({
    queryKey: ["admin_bootstrap_status"],
    queryFn: fetchBootstrapStatus,
    enabled: canAccess,
  });

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
      setSignOutError(t.admin.security.signOutError);
    } finally {
      setIsSigningOut(false);
    }
  };

  const handleChangePassword = async () => {
    setPasswordMessage(null);
    setPasswordError(null);

    if (newPassword.length < 8) {
      setPasswordError(t.admin.security.changePassword.errorLength);
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t.admin.security.changePassword.errorMismatch);
      return;
    }

    setIsChangingPassword(true);
    try {
      const response = await fetchAuthApi("/api/admin/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPassword }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw new Error(payload.detail ?? t.admin.security.changePassword.errorFailed);
      }

      setNewPassword("");
      setConfirmPassword("");
      setPasswordMessage(t.admin.security.changePassword.successMessage);

      await logout();

      clearTenantId();
      await queryClient.cancelQueries();
      queryClient.clear();
      router.replace("/sign-in");
      router.refresh();
      window.location.assign("/sign-in");
    } catch (error) {
      setPasswordError(
        error instanceof Error ? error.message : t.admin.security.changePassword.errorFailed,
      );
    } finally {
      setIsChangingPassword(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto w-full">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">{t.admin.security.title}</h1>
        <p className="text-zinc-500 mt-1">{t.admin.security.description}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Bootstrap 状态卡片 */}
        <div className="p-6 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-white dark:bg-zinc-900">
          <div className="flex items-center gap-3 mb-4 text-indigo-600 dark:text-indigo-400">
            <ShieldCheckIcon className="size-5" />
            <h2 className="font-semibold text-zinc-900 dark:text-zinc-100">
              {t.admin.security.cards.bootstrapStatus}
            </h2>
          </div>

          <div className="space-y-4 text-sm">
            <div className="flex justify-between items-center py-2 border-b border-zinc-100 dark:border-zinc-800">
              <span className="text-zinc-500">{t.admin.security.fields.bootstrapAdmin}</span>
              {isLoading ? (
                 <span className="text-zinc-400">Loading...</span>
              ) : statusData?.is_bootstrap_admin ? (
                 <span className="text-indigo-600 font-medium bg-indigo-50 px-2 py-1 rounded">{t.admin.security.fields.yes}</span>
              ) : (
                 <span className="text-zinc-600">{t.admin.security.fields.no}</span>
              )}
            </div>

            <div className="flex justify-between items-center py-2 border-b border-zinc-100 dark:border-zinc-800">
              <span className="text-zinc-500">{t.admin.security.fields.mustChangePassword}</span>
              {isLoading ? (
                 <span className="text-zinc-400">Loading...</span>
              ) : statusData?.must_change_password ? (
                 <span className="text-red-600 font-medium bg-red-50 px-2 py-1 rounded flex items-center gap-1">
                   <AlertTriangleIcon className="size-4" /> {t.admin.security.fields.needChange}
                 </span>
              ) : (
                 <span className="text-green-600 font-medium bg-green-50 px-2 py-1 rounded">{t.admin.security.fields.completed}</span>
              )}
            </div>

            <div className="pt-2 space-y-2">
              <input
                type="password"
                placeholder={t.admin.security.changePassword.newPasswordPlaceholder}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="h-9 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-zinc-700 dark:bg-zinc-800"
              />
              <input
                type="password"
                placeholder={t.admin.security.changePassword.confirmPasswordPlaceholder}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="h-9 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-zinc-700 dark:bg-zinc-800"
              />
              <Button
                className="w-full"
                onClick={() => void handleChangePassword()}
                disabled={isChangingPassword}
              >
                {isChangingPassword ? t.admin.security.changePassword.submitting : t.admin.security.changePassword.submit}
              </Button>
              {passwordMessage && (
                <p className="text-sm text-emerald-600">{passwordMessage}</p>
              )}
              {passwordError && (
                <p className="text-sm text-red-600">{passwordError}</p>
              )}
            </div>
          </div>
        </div>

        {/* 密钥状态卡片 */}
        <div className="p-6 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-white dark:bg-zinc-900">
          <div className="flex items-center gap-3 mb-4 text-indigo-600 dark:text-indigo-400">
            <KeyIcon className="size-5" />
            <h2 className="font-semibold text-zinc-900 dark:text-zinc-100">
              {t.admin.security.cards.keyStatus}
            </h2>
          </div>

          <div className="space-y-4 text-sm">
            <div className="flex justify-between items-center py-2 border-b border-zinc-100 dark:border-zinc-800">
              <span className="text-zinc-500">{t.admin.security.keyStatus.trustedOrigins}</span>
              <span className="text-green-600 font-mono text-xs bg-green-50 px-2 py-1 rounded">{t.admin.security.keyStatus.configured}</span>
            </div>

            <div className="flex justify-between items-center py-2 border-b border-zinc-100 dark:border-zinc-800">
              <span className="text-zinc-500">{t.admin.security.keyStatus.secretsEncryption}</span>
              <span className="text-zinc-500 italic">{t.admin.security.keyStatus.notConfigured}</span>
            </div>
            
            <div className="flex justify-between items-center py-2 border-b border-zinc-100 dark:border-zinc-800">
              <span className="text-zinc-500">{t.admin.security.keyStatus.uploadLimit}</span>
              <span className="text-zinc-900 font-mono text-xs">{t.admin.security.keyStatus.defaultSoftLimit}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 p-6 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-white dark:bg-zinc-900">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="font-semibold text-zinc-900 dark:text-zinc-100">{t.admin.security.signOutCard.title}</h2>
            <p className="text-sm text-zinc-500 mt-1">{t.admin.security.signOutCard.description}</p>
          </div>
          <Button
            variant="destructive"
            onClick={() => void handleSignOut()}
            disabled={isSigningOut}
          >
            {isSigningOut ? t.admin.security.signOutCard.signingOut : t.admin.security.signOutCard.button}
          </Button>
        </div>
        {signOutError && (
          <p className="text-destructive text-sm mt-3">{signOutError}</p>
        )}
      </div>
    </div>
  );
}
