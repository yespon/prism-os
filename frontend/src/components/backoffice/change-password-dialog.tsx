"use client";

import { useQueryClient } from "@tanstack/react-query";
import { KeyRoundIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { fetchAuthApi } from "@/core/api/auth-client";
import { logout } from "@/core/auth/auth-api";
import { useI18n } from "@/core/i18n/hooks";
import { clearTenantId } from "@/core/tenants";

interface ChangePasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChangePasswordDialog({
  open,
  onOpenChange,
}: ChangePasswordDialogProps) {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isChanging, setIsChanging] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleClose = () => {
    setNewPassword("");
    setConfirmPassword("");
    setMessage(null);
    setError(null);
    onOpenChange(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setError(null);

    if (newPassword.length < 8) {
      setError(t.auth.changePassword.errorLength);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError(t.auth.changePassword.errorMismatch);
      return;
    }

    setIsChanging(true);
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
        throw new Error(payload.detail ?? t.auth.changePassword.errorChangeFailed);
      }

      setMessage(t.admin.security.changePassword.successMessage);

      // Sign out after delay and redirect to sign-in
      setTimeout(() => {
        void (async () => {
          await logout();

          clearTenantId();
          await queryClient.cancelQueries();
          queryClient.clear();
          router.replace("/sign-in");
          router.refresh();
          window.location.assign("/sign-in");
        })();
      }, 1500);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : t.auth.changePassword.errorChangeFailed
      );
    } finally {
      setIsChanging(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRoundIcon className="size-5" />
            {t.auth.changePassword.title}
          </DialogTitle>
          <DialogDescription>
            {t.auth.changePassword.description}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          <div className="space-y-2">
            <label className="text-sm font-medium">{t.auth.changePassword.newPassword}</label>
            <Input
              type="password"
              placeholder={t.auth.changePassword.newPasswordPlaceholder}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={isChanging}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">{t.auth.changePassword.confirmPassword}</label>
            <Input
              type="password"
              placeholder={t.auth.changePassword.confirmPasswordPlaceholder}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isChanging}
            />
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">
              {error}
            </div>
          )}

          {message && (
            <div className="text-sm text-emerald-600 bg-emerald-50 px-3 py-2 rounded">
              {message}
            </div>
          )}

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={isChanging}
            >
              {t.common.cancel}
            </Button>
            <Button type="submit" disabled={isChanging || !newPassword || !confirmPassword}>
              {isChanging ? t.auth.changePassword.saving : t.auth.changePassword.submitButton}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
