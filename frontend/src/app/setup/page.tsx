"use client";

import { AlertCircleIcon, ArrowRightIcon, ShieldCheckIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthLocaleSwitcher } from "@/components/auth/locale-switcher";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchAuthApi } from "@/core/api/auth-client";
import { login } from "@/core/auth/auth-api";
import { useI18n } from "@/core/i18n/hooks";

interface BootstrapStatus {
  needs_setup: boolean;
  bootstrap_user_id: string | null;
}

export default function SetupPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [status, setStatus] = useState<BootstrapStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchAuthApi("/api/auth/bootstrap-status")
      .then((res) => res.json())
      .then((data: BootstrapStatus) => {
        setStatus(data);
        if (!data.needs_setup) {
          router.replace("/sign-in");
        }
      })
      .catch(() => setError(t.auth.setup.errorCheckStatus))
      .finally(() => setStatusLoading(false));
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email?.includes("@")) {
      setError(t.auth.setup.errorInvalidEmail);
      return;
    }
    if (password.length < 8) {
      setError(t.auth.setup.errorPasswordLength);
      return;
    }
    if (password !== confirmPassword) {
      setError(t.auth.setup.errorPasswordMismatch);
      return;
    }
    if (!status?.bootstrap_user_id) {
      setError(t.auth.setup.errorSystemStatus);
      return;
    }

    setIsSubmitting(true);

    try {
      const setupRes = await fetchAuthApi("/api/auth/setup-bootstrap-admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: status.bootstrap_user_id,
          email: email.trim().toLowerCase(),
          password,
        }),
      });

      if (!setupRes.ok) {
        const data = await setupRes.json().catch(() => ({}));
        throw new Error(data.detail ?? t.auth.setup.errorInitFailed);
      }

      const result = await login(email.trim().toLowerCase(), password);

      if (result.error) {
        throw new Error(result.error.message ?? t.auth.setup.errorAutoLoginFailed);
      }

      router.replace("/admin");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.auth.setup.errorRetry);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (statusLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  if (!status?.needs_setup) {
    return null;
  }

  return (
    <div className="relative flex min-h-screen w-full items-center justify-center bg-zinc-50 dark:bg-zinc-950 p-4">
      <div className="absolute top-4 right-4">
        <AuthLocaleSwitcher />
      </div>
      <Card className="w-full max-w-md shadow-lg border-zinc-200 dark:border-zinc-800">
        <CardHeader className="space-y-3 pb-6 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/30">
            <ShieldCheckIcon className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
          </div>
          <CardTitle className="text-2xl font-bold tracking-tight">
            {t.auth.setup.title}
          </CardTitle>
          <CardDescription className="text-sm">
            {t.auth.setup.description}
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4 pb-2">
            {error && (
              <div className="flex items-center gap-2 rounded-lg bg-red-50 dark:bg-red-950/50 p-3 text-sm text-red-600 dark:text-red-400">
                <AlertCircleIcon className="h-4 w-4 shrink-0" />
                <p>{error}</p>
              </div>
            )}
            <div className="space-y-2">
              <label className="text-sm font-medium text-zinc-900 dark:text-zinc-300">
                {t.auth.setup.email}
              </label>
              <Input
                type="email"
                placeholder={t.auth.setup.emailPlaceholder}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isSubmitting}
                className="h-11"
                autoComplete="email"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-zinc-900 dark:text-zinc-300">
                {t.auth.setup.password}
              </label>
              <Input
                type="password"
                placeholder={t.auth.setup.passwordPlaceholder}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isSubmitting}
                className="h-11"
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-zinc-900 dark:text-zinc-300">
                {t.auth.setup.confirmPassword}
              </label>
              <Input
                type="password"
                placeholder={t.auth.setup.confirmPasswordPlaceholder}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={isSubmitting}
                className="h-11"
                autoComplete="new-password"
              />
            </div>
          </CardContent>
          <CardFooter className="pt-6">
            <Button
              type="submit"
              className="w-full h-11"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                t.auth.setup.initializing
              ) : (
                <>
                  {t.auth.setup.submitButton}
                  <ArrowRightIcon className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
