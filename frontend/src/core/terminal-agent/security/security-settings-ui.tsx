'use client';

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Shield,
  Settings2,
  X,
  Download,
  Upload,
  RotateCcw,
  AlertTriangle,
} from 'lucide-react';
import { useEffect } from 'react';
import { fetchAuthApi } from '@/core/api/auth-client';
import {
  DEFAULT_SECURITY_CONFIG,
  type SecurityConfig,
} from './security-config';
import {
  DEFAULT_AUTO_APPROVAL,
  type AutoApprovalSettings,
} from './auto-approval-settings';

interface SecuritySettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

export function SecuritySettingsPanel({ open, onClose }: SecuritySettingsPanelProps) {
  const [securityConfig, setSecurityConfig] = useState<SecurityConfig>(DEFAULT_SECURITY_CONFIG);
  const [autoSettings, setAutoSettings] = useState<AutoApprovalSettings>(DEFAULT_AUTO_APPROVAL);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setLoading(true);
      fetchAuthApi('/api/v1/terminal/security-settings')
        .then((res) => {
          if (!res.ok) throw new Error('Failed to load settings');
          return res.json();
        })
        .then((data) => {
          if (data.security_config) {
            setSecurityConfig(data.security_config);
          }
          if (data.auto_approval) {
            setAutoSettings(data.auto_approval);
          }
        })
        .catch((err) => console.error('Failed to load security settings', err))
        .finally(() => setLoading(false));
    }
  }, [open]);

  if (!open) return null;

  const saveSettings = async (cfg: SecurityConfig, auto: AutoApprovalSettings) => {
    try {
      const res = await fetchAuthApi('/api/v1/terminal/security-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          security_config: cfg,
          auto_approval: auto,
        }),
      });
      if (!res.ok) {
        console.error('Failed to save settings:', res.statusText);
      }
    } catch (err) {
      console.error('Failed to save settings:', err);
    }
  };

  const updateSecurity = (updates: Partial<SecurityConfig>) => {
    setSecurityConfig((prev) => {
      const next = {
        ...prev,
        ...updates,
        securityPolicy: updates.securityPolicy
          ? { ...prev.securityPolicy, ...updates.securityPolicy }
          : prev.securityPolicy,
      };
      saveSettings(next, autoSettings);
      return next;
    });
  };

  const updateAuto = (updates: Partial<AutoApprovalSettings>) => {
    setAutoSettings((prev) => {
      const next = {
        ...prev,
        ...updates,
        actions: updates.actions
          ? { ...prev.actions, ...updates.actions }
          : prev.actions,
      };
      saveSettings(securityConfig, next);
      return next;
    });
  };

  const handleExport = () => {
    const json = JSON.stringify({ security_config: securityConfig, auto_approval: autoSettings }, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'prismos-security-config.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e: any) => {
      const file = e.target?.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const parsed = JSON.parse(reader.result as string);
          if (parsed.security_config && parsed.auto_approval) {
            setSecurityConfig(parsed.security_config);
            setAutoSettings(parsed.auto_approval);
            await saveSettings(parsed.security_config, parsed.auto_approval);
          } else {
            alert('无效的配置文件格式');
          }
        } catch {
          alert('无效的配置文件格式');
        }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  const handleReset = async () => {
    if (confirm('确定要恢复默认安全配置吗？')) {
      try {
        const res = await fetchAuthApi('/api/v1/terminal/security-settings/reset', {
          method: 'POST',
        });
        if (res.ok) {
          const data = await res.json();
          if (data.security_config) setSecurityConfig(data.security_config);
          if (data.auto_approval) setAutoSettings(data.auto_approval);
        }
      } catch (err) {
        console.error('Failed to reset settings:', err);
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-[420px] h-full bg-white shadow-2xl border-l border-zinc-200 overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-zinc-200 px-5 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-blue-600" />
            <h2 className="font-semibold text-sm text-zinc-900">安全与自动审批设置</h2>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-6">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
            <div className="flex items-start gap-2">
              <Shield className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
              <p className="text-xs text-blue-700">
                命令执行以服务端安全策略为准。本页配置用于本地偏好和后续策略同步展示，危险操作仍会由服务端拦截或要求确认。
              </p>
            </div>
          </div>

          {/* ============================================
              Section 1: Command Security
              ============================================ */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">
              命令安全
            </h3>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-zinc-800">启用命令安全检查</span>
                  <p className="text-xs text-zinc-400 mt-0.5">在执行命令前进行安全验证</p>
                </div>
                <Switch
                  checked={securityConfig.enableCommandSecurity}
                  onCheckedChange={(v) => updateSecurity({ enableCommandSecurity: v })}
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-zinc-800">严格模式</span>
                  <p className="text-xs text-zinc-400 mt-0.5">仅允许白名单中的命令执行</p>
                </div>
                <Switch
                  checked={securityConfig.enableStrictMode}
                  onCheckedChange={(v) => updateSecurity({ enableStrictMode: v })}
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-zinc-800">高危命令：询问用户</span>
                  <p className="text-xs text-zinc-400 mt-0.5">systemctl, chmod, chown 等高危命令</p>
                </div>
                <Switch
                  checked={securityConfig.securityPolicy.askForHigh}
                  onCheckedChange={(v) =>
                    updateSecurity({ securityPolicy: { ...securityConfig.securityPolicy, askForHigh: v } })
                  }
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-zinc-800">中危命令：询问用户</span>
                  <p className="text-xs text-zinc-400 mt-0.5">iptables, sudo, su 等中危命令</p>
                </div>
                <Switch
                  checked={securityConfig.securityPolicy.askForMedium}
                  onCheckedChange={(v) =>
                    updateSecurity({ securityPolicy: { ...securityConfig.securityPolicy, askForMedium: v } })
                  }
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-zinc-800">最大命令长度</span>
                  <p className="text-xs text-zinc-400 mt-0.5">当前: {securityConfig.maxCommandLength} 字符</p>
                </div>
                <select
                  value={securityConfig.maxCommandLength}
                  onChange={(e) => updateSecurity({ maxCommandLength: parseInt(e.target.value) })}
                  className="text-xs border border-zinc-200 rounded px-2 py-1"
                >
                  <option value="1000">1,000</option>
                  <option value="5000">5,000</option>
                  <option value="10000">10,000</option>
                  <option value="50000">50,000</option>
                </select>
              </div>
            </div>
          </section>

          {/* ============================================
              Section 2: Auto-Approval
              ============================================ */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">
              自动审批
            </h3>

            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-700">
                  自动审批会让 Agent 自动执行命令而不等待你的确认。请谨慎启用。
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-zinc-800">启用自动审批</span>
                  <p className="text-xs text-zinc-400 mt-0.5">符合策略的命令自动执行</p>
                </div>
                <Switch
                  checked={autoSettings.enabled}
                  onCheckedChange={(v) => updateAuto({ enabled: v })}
                />
              </div>

              {autoSettings.enabled && (
                <>
                  <div className="flex items-center justify-between pl-4">
                    <span className="text-sm text-zinc-700">自动读取文件</span>
                    <Switch
                      checked={autoSettings.actions.readFiles}
                      onCheckedChange={(v) => updateAuto({ actions: { ...autoSettings.actions, readFiles: v } })}
                    />
                  </div>
                  <div className="flex items-center justify-between pl-4">
                    <span className="text-sm text-zinc-700">自动编辑文件</span>
                    <Switch
                      checked={autoSettings.actions.editFiles}
                      onCheckedChange={(v) => updateAuto({ actions: { ...autoSettings.actions, editFiles: v } })}
                    />
                  </div>
                  <div className="flex items-center justify-between pl-4">
                    <span className="text-sm text-zinc-700">自动执行安全命令</span>
                    <Switch
                      checked={autoSettings.actions.executeSafeCommands}
                      onCheckedChange={(v) => updateAuto({ actions: { ...autoSettings.actions, executeSafeCommands: v } })}
                    />
                  </div>
                  <div className="flex items-center justify-between pl-4">
                    <div>
                      <span className="text-sm text-zinc-700">自动执行所有命令</span>
                      <p className="text-xs text-red-500 mt-0.5">⚠️ 包括危险命令，极度危险</p>
                    </div>
                    <Switch
                      checked={autoSettings.actions.executeAllCommands}
                      onCheckedChange={(v) => updateAuto({ actions: { ...autoSettings.actions, executeAllCommands: v } })}
                    />
                  </div>
                  <div className="flex items-center justify-between pl-4">
                    <span className="text-sm text-zinc-700">首次批准后自动执行只读命令</span>
                    <Switch
                      checked={autoSettings.actions.autoExecuteReadOnlyCommands}
                      onCheckedChange={(v) =>
                        updateAuto({ actions: { ...autoSettings.actions, autoExecuteReadOnlyCommands: v } })
                      }
                    />
                  </div>
                  <div className="flex items-center justify-between pl-4">
                    <div>
                      <span className="text-sm text-zinc-700">最大连续自动批准次数</span>
                      <p className="text-xs text-zinc-400 mt-0.5">防止无限循环</p>
                    </div>
                    <select
                      value={autoSettings.maxRequests}
                      onChange={(e) => updateAuto({ maxRequests: parseInt(e.target.value) })}
                      className="text-xs border border-zinc-200 rounded px-2 py-1"
                    >
                      {[1, 2, 3, 5, 10, 20].map((n) => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}
            </div>
          </section>

          {/* ============================================
              Section 3: Config Management
              ============================================ */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">
              配置管理
            </h3>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={handleExport}
              >
                <Download className="w-3 h-3 mr-1" />
                导出配置
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={handleImport}
              >
                <Upload className="w-3 h-3 mr-1" />
                导入配置
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs text-red-500 hover:text-red-700 hover:bg-red-50"
                onClick={handleReset}
              >
                <RotateCcw className="w-3 h-3 mr-1" />
                恢复默认
              </Button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
