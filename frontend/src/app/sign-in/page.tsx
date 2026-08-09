"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { AuthLocaleSwitcher } from "@/components/auth/locale-switcher";
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
import { login, logout } from "@/core/auth/auth-api";
import { useI18n } from "@/core/i18n/hooks";
import type { TenantItem } from "@/core/tenants";

// 浮动粒子背景组件
function FloatingNodes() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <svg className="h-full w-full" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#06B6D4" stopOpacity="0" />
            <stop offset="50%" stopColor="#06B6D4" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#7C3AED" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* 节点 */}
        {[
          { cx: 15, cy: 25, r: 3, delay: 0 },
          { cx: 25, cy: 40, r: 2, delay: 1 },
          { cx: 35, cy: 20, r: 2.5, delay: 2 },
          { cx: 45, cy: 35, r: 2, delay: 0.5 },
          { cx: 55, cy: 28, r: 3, delay: 1.5 },
          { cx: 65, cy: 42, r: 2, delay: 2.5 },
          { cx: 75, cy: 22, r: 2.5, delay: 0.8 },
          { cx: 85, cy: 38, r: 2, delay: 1.8 },
        ].map((node, i) => (
          <g key={i}>
            <circle
              cx={`${node.cx}%`}
              cy={`${node.cy}%`}
              r={node.r}
              fill="#06B6D4"
              opacity="0.4"
            >
              <animate
                attributeName="opacity"
                values="0.4;0.8;0.4"
                dur="3s"
                begin={`${node.delay}s`}
                repeatCount="indefinite"
              />
              <animate
                attributeName="r"
                values={`${node.r};${node.r + 1};${node.r}`}
                dur="3s"
                begin={`${node.delay}s`}
                repeatCount="indefinite"
              />
            </circle>
          </g>
        ))}
        {/* 连线 */}
        {[
          { x1: 15, y1: 25, x2: 25, y2: 40 },
          { x1: 25, y1: 40, x2: 35, y2: 20 },
          { x1: 35, y1: 20, x2: 45, y2: 35 },
          { x1: 45, y1: 35, x2: 55, y2: 28 },
          { x1: 55, y1: 28, x2: 65, y2: 42 },
          { x1: 65, y1: 42, x2: 75, y2: 22 },
          { x1: 75, y1: 22, x2: 85, y2: 38 },
        ].map((line, i) => (
          <line
            key={i}
            x1={`${line.x1}%`}
            y1={`${line.y1}%`}
            x2={`${line.x2}%`}
            y2={`${line.y2}%`}
            stroke="url(#lineGrad)"
            strokeWidth="1"
            opacity="0.3"
          >
            <animate
              attributeName="opacity"
              values="0.1;0.4;0.1"
              dur="4s"
              begin={`${i * 0.3}s`}
              repeatCount="indefinite"
            />
          </line>
        ))}
      </svg>
    </div>
  );
}

export default function SignInPage() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focusedField, setFocusedField] = useState<string | null>(null);
  const [showNoTenantDialog, setShowNoTenantDialog] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // 检测是否从注册页跳转过来
  const justRegistered = searchParams.get("registered") === "true";

  // 图标浮动动画
  const [floatY, setFloatY] = useState(0);
  useEffect(() => {
    let animationId: number;
    let startTime: number;

    const animate = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      // 正弦波浮动
      const y = Math.sin(elapsed / 1500) * 8;
      setFloatY(y);
      animationId = requestAnimationFrame(animate);
    };

    animationId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationId);
  }, []);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const input = email.trim();
      if (!input) {
        setError(t.auth.signIn.errorEmptyEmail);
        return;
      }

      if (!input.includes("@")) {
        setError(t.auth.signIn.errorInvalidEmail);
        return;
      }

      const result = await login(input, password);

      if (result.error) {
        setError(result.error.message ?? t.auth.signIn.errorLoginFailed);
        return;
      }

      const user = result.data?.user;
      if (user?.role === "admin" && user.mustChangePassword) {
        router.push("/change-password");
        router.refresh();
        return;
      }

      if (user?.role === "admin") {
        router.push("/admin");
        router.refresh();
        return;
      }

      try {
        const response = await fetchAuthApi("/api/tenants");
        if (response.ok) {
          const payload = (await response.json()) as { tenants?: TenantItem[] };
          const tenants = payload.tenants ?? [];
          if (tenants.length === 0) {
            await logout();
            setShowNoTenantDialog(true);
            return;
          }
          if (tenants.length > 1) {
            router.push("/select-workspace?next=/workspace/overview");
            router.refresh();
            return;
          }
        } else if (response.status === 403) {
          await logout();
          setShowNoTenantDialog(true);
          return;
        }
      } catch (err) {
        console.warn("Failed to check tenants during login", err);
      }

      router.push("/workspace/overview");
      router.refresh();
    } catch {
      setError(t.auth.signIn.errorRetry);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-white dark:bg-zinc-950">
      {/* 左侧 - 品牌展示 */}
      <div className="hidden lg:flex lg:w-[55%] relative overflow-hidden bg-zinc-950">
        {/* 渐变背景 */}
        <div className="absolute inset-0 bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950" />
        
        {/* 浮动节点网络 */}
        <FloatingNodes />
        
        {/* 中央光晕 */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <div className="h-96 w-96 rounded-full bg-gradient-to-r from-cyan-500/10 to-purple-500/10 blur-3xl" />
        </div>

        <div className="relative z-10 flex flex-col justify-center items-center w-full p-12">
          {/* 浮动图标 */}
          <div 
            className="relative transition-transform duration-100"
            style={{ transform: `translateY(${floatY}px)` }}
          >
            <img
              src="/images/prismos.svg"
              alt="PrismOS"
              className="h-36 w-36 xl:h-44 xl:w-44 drop-shadow-[0_0_40px_rgba(6,182,212,0.3)]"
            />
            {/* 图标光晕 */}
            <div className="absolute inset-0 -z-10 blur-2xl">
              <img
                src="/images/prismos.svg"
                alt=""
                className="h-36 w-36 xl:h-44 xl:w-44 opacity-30"
              />
            </div>
          </div>
          
          {/* 品牌信息 */}
          <div className="mt-10 text-center">
            <h1 className="text-3xl xl:text-4xl font-bold tracking-tight text-white">
              PrismOS
            </h1>
            <p className="mt-3 text-sm text-zinc-400 font-medium tracking-[0.2em] uppercase">
              {t.auth.signIn.brandTagline}
            </p>
          </div>

          {/* 动态特性卡片 */}
          <div className="mt-14 flex gap-4">
            {[
              { icon: "◆", text: t.auth.signIn.feature1, color: "cyan" },
              { icon: "◎", text: t.auth.signIn.feature2, color: "purple" },
              { icon: "◈", text: t.auth.signIn.feature3, color: "blue" },
            ].map((item, i) => (
              <div
                key={item.text}
                className="group relative overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50 px-5 py-3 backdrop-blur-sm transition-all duration-300 hover:border-zinc-700 hover:bg-zinc-800/50"
                style={{ animationDelay: `${i * 100}ms` }}
              >
                <div className="flex items-center gap-2">
                  <span className={`text-${item.color}-400`}>{item.icon}</span>
                  <span className="text-sm font-medium text-zinc-300">{item.text}</span>
                </div>
                {/* 悬停光效 */}
                <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/5 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
              </div>
            ))}
          </div>
        </div>

        {/* 底部装饰 */}
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-zinc-950 to-transparent" />
      </div>

      {/* 右侧 - 登录表单 */}
      <div className="relative flex w-full lg:w-[45%] items-center justify-center p-6 lg:p-12 bg-zinc-50 dark:bg-zinc-950">
        {/* 语言切换 */}
        <div className="absolute top-4 right-4">
          <AuthLocaleSwitcher />
        </div>
        <div className="w-full max-w-sm">
          {/* 移动端 Logo */}
          <div className="flex flex-col items-center mb-10 lg:hidden">
            <img
              src="/images/prismos.svg"
              alt="PrismOS"
              className="h-16 w-16"
            />
            <h1 className="mt-4 text-xl font-bold text-zinc-900 dark:text-zinc-100">
              PrismOS
            </h1>
          </div>

          {/* 标题 */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
              {t.auth.signIn.welcomeBack}
            </h2>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              {t.auth.signIn.signInWithEmail}
            </p>
          </div>

          {/* 注册成功提示 */}
          {justRegistered && (
            <div className="mb-6 flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700 animate-in fade-in slide-in-from-top-2 dark:border-green-900 dark:bg-green-950/30 dark:text-green-400">
              <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="font-medium">{t.auth.signIn.registerSuccess}</p>
                <p className="text-green-600/80 dark:text-green-500/80">{t.auth.signIn.registerSuccessDesc}</p>
              </div>
            </div>
          )}

          {/* 表单 */}
          <form className="space-y-5" onSubmit={onSubmit}>
            <div className="space-y-2">
              <label
                htmlFor="email"
                className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t.auth.signIn.email}
              </label>
              <div className="relative">
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setFocusedField('email')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="you@company.com"
                  className="h-12 rounded-xl border-zinc-200 bg-white px-4 pr-10 transition-all duration-300 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 dark:border-zinc-800 dark:bg-zinc-900 dark:focus:border-cyan-500"
                  required
                  autoComplete="email"
                />
                {/* 聚焦指示器 */}
                <div className={`absolute right-3 top-1/2 -translate-y-1/2 transition-all duration-300 ${focusedField === 'email' ? 'opacity-100 scale-100' : 'opacity-0 scale-75'}`}>
                  <div className="h-2 w-2 rounded-full bg-cyan-500 animate-pulse" />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <label
                htmlFor="password"
                className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t.auth.signIn.password}
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="••••••••"
                  className="h-12 rounded-xl border-zinc-200 bg-white px-4 pr-10 transition-all duration-300 focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 dark:border-zinc-800 dark:bg-zinc-900 dark:focus:border-purple-500"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300 transition-colors"
                >
                  {showPassword ? (
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  ) : (
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600 animate-in fade-in slide-in-from-top-2 dark:bg-red-950/30 dark:text-red-400">
                <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {error}
              </div>
            )}

            <Button
              type="submit"
              className="group relative h-12 w-full overflow-hidden rounded-xl bg-zinc-900 text-base font-semibold text-white transition-all hover:bg-zinc-800 hover:shadow-lg hover:shadow-zinc-900/20 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-100"
              disabled={isSubmitting}
            >
              {/* 按钮光效 */}
              <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
              
              {isSubmitting ? (
                <span className="flex items-center gap-2">
                  <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  {t.auth.signIn.connecting}
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  {t.auth.signIn.loginButton}
                  <svg className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </span>
              )}
            </Button>
          </form>

          {/* 注册链接 */}
          <div className="mt-8 text-center">
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t.auth.signIn.newUser}{" "}
              <Link
                href="/sign-up"
                className="font-semibold text-zinc-900 transition-colors hover:text-cyan-600 dark:text-zinc-100 dark:hover:text-cyan-400"
              >
                {t.auth.signIn.register}
              </Link>
            </p>
          </div>
        </div>
      </div>

      {/* 未绑定工作空间提示弹窗 */}
      <Dialog open={showNoTenantDialog} onOpenChange={setShowNoTenantDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-600">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              {t.auth.signIn.accountNotActive}
            </DialogTitle>
            <DialogDescription className="pt-2">
              {t.auth.signIn.accountNotActiveDesc}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button 
              onClick={() => setShowNoTenantDialog(false)}
              className="w-full"
            >
              {t.auth.signIn.iUnderstand}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}
