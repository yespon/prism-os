import { Loader2, CheckCircle2, XCircle, Eye, EyeOff, X } from 'lucide-react';
import React, { useState, useRef } from 'react';
import { AssetOperationError, requestAssetOperation } from '@/core/terminal-agent/assets-api';
import { useSkillQueryIdentity } from '@/core/skills/query-identity';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { TerminalAsset, TerminalAssetGroup, TerminalAssetInput, TerminalCredential } from '@/core/terminal-agent/message-types';

interface HostFormData {
  name: string;
  ip: string;
  port: string;
  username: string;
  keychain_id: string;
  group_id: string;
  password: string;
}

export interface AddHostDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAddHost?: (host: TerminalAssetInput) => void | Promise<void>;
  onEditHost?: (id: string, host: TerminalAssetInput) => void | Promise<void>;
  editAsset?: TerminalAsset | null;
  credentials?: TerminalCredential[];
  groups?: TerminalAssetGroup[];
  onAddCredentialClick?: () => void;
}

export function AddHostDialog({ open, onOpenChange, onAddHost, onEditHost, editAsset, credentials = [], groups = [], onAddCredentialClick }: AddHostDialogProps) {
  const identity = useSkillQueryIdentity();
  const [formData, setFormData] = useState<HostFormData>({
    name: '',
    ip: '',
    port: '22',
    username: 'root',
    keychain_id: '',
    group_id: '',
    password: ''
  });
  
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');

  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [testLog, setTestLog] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveUnknown, setSaveUnknown] = useState(false);
  const [testUnknown, setTestUnknown] = useState(false);
  const submitting = useRef(false);
  const testing = useRef(false);

  React.useEffect(() => {
    if (open) {
      if (editAsset) {
        setFormData({
          name: editAsset.name ?? '',
          ip: editAsset.ip ?? '',
          port: String(editAsset.port ?? '22'),
          username: editAsset.username ?? 'root',
          keychain_id: editAsset.keychain_id ?? '',
          group_id: editAsset.group_id ?? '',
          password: '' // Don't prefill password for security
        });
      } else {
        setFormData({
          name: '',
          ip: '',
        port: '22',
          username: 'root',
          keychain_id: '',
          group_id: '',
          password: ''
        });
      }
      setTestStatus('idle');
      setTestLog('');
      setIsCreatingGroup(false);
      setNewGroupName('');
    }
  }, [open, editAsset]);

  const handleTestConnection = async () => {
    if (testing.current || testUnknown) return;
    testing.current = true;
    setTestStatus('testing');
    try {
      const data = await requestAssetOperation<{ status: string; message?: string }>(
        '/api/v1/assets/test-connection', 'POST', { ...formData, port: parseInt(formData.port, 10) || 22 }, identity.isCurrent,
      );
      setTestStatus(data.status === 'ok' ? 'success' : 'error');
      setTestLog(data.message ?? (data.status === 'ok' ? '连接测试成功' : '连接测试失败'));
    } catch (error) {
      setTestStatus('error');
      setTestUnknown(!(error instanceof AssetOperationError) || error.inspectionRequired);
      setTestLog(error instanceof AssetOperationError ? error.message : '连接结果未确认，请先核对。');
    } finally {
      testing.current = false;
    }
  };

  const handleSubmit = async () => {
    if (submitting.current || saveUnknown || !identity.isCurrent()) return;
    submitting.current = true;
    setSaving(true);
    try {
      let finalGroupId = formData.group_id;
      if (isCreatingGroup && newGroupName.trim()) {
        const group = await requestAssetOperation<{ id: string }>('/api/v1/assets/groups', 'POST', { name: newGroupName.trim() }, identity.isCurrent);
        if (!group.id) throw new AssetOperationError('分组结果未确认，请先刷新列表核对。', true);
        finalGroupId = group.id;
        setFormData(current => ({ ...current, group_id: group.id }));
        setIsCreatingGroup(false);
        setNewGroupName('');
      }
      const payload: TerminalAssetInput = { ...formData, port: parseInt(formData.port, 10) || 22, group_id: finalGroupId ?? null };
      if (!identity.isCurrent()) throw new AssetOperationError("身份已变化，请核对原操作结果。", true);
      if (editAsset && onEditHost) await onEditHost(editAsset.id, payload);
      else if (onAddHost) await onAddHost(payload);
      else return;
      onOpenChange(false);
    } catch (error) {
      setSaveUnknown(!(error instanceof AssetOperationError) || error.inspectionRequired);
      setTestStatus('error');
      setTestLog(error instanceof AssetOperationError ? error.message : '保存结果未确认，请先刷新列表核对。');
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{editAsset ? '编辑主机' : '添加主机'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <label className="text-sm font-medium">名称/别名</label>
            <Input 
              placeholder="例如：生产环境-DB" 
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-2 grid gap-2">
              <label className="text-sm font-medium">IP 地址</label>
              <Input 
                placeholder="192.168.1.1" 
                value={formData.ip}
                onChange={(e) => setFormData({ ...formData, ip: e.target.value })}
              />
            </div>
            <div className="col-span-1 grid gap-2">
              <label className="text-sm font-medium">端口</label>
              <Input 
                placeholder="22" 
                value={formData.port}
                onChange={(e) => setFormData({ ...formData, port: e.target.value })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <label className="text-sm font-medium">用户名</label>
              <Input 
                placeholder="root" 
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <label className="text-sm font-medium">所属分组</label>
              {isCreatingGroup ? (
                <div className="flex items-center gap-2">
                  <Input 
                    autoFocus 
                    placeholder="输入新分组名称" 
                    value={newGroupName} 
                    onChange={(e) => setNewGroupName(e.target.value)} 
                  />
                  <Button variant="ghost" size="icon" onClick={() => {
                    setIsCreatingGroup(false);
                    setNewGroupName('');
                    setFormData({ ...formData, group_id: '' });
                  }}>
                    <X className="w-4 h-4 text-zinc-400" />
                  </Button>
                </div>
              ) : (
                <Select 
                  value={formData.group_id || 'none'} 
                  onValueChange={(val) => {
                    if (val === 'new_group') {
                      setIsCreatingGroup(true);
                      setFormData({ ...formData, group_id: '' });
                    } else {
                      setFormData({ ...formData, group_id: val === 'none' ? '' : val });
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="未分组" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">未分组</SelectItem>
                    {groups.map(g => (
                      <SelectItem key={g.id} value={g.id}>{g.name}</SelectItem>
                    ))}
                    <SelectItem value="new_group" className="text-blue-600 font-medium">+ 新建分组...</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">服务器密码</label>
            <div className="relative mt-1">
              <Input 
                type={showPassword ? "text" : "password"}
                placeholder="直接输入服务器密码" 
                className="pr-10"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 focus:outline-none"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          
          {testStatus !== 'idle' && (
            <div className={`p-3 rounded-lg text-xs font-mono break-all ${
              testStatus === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
              testStatus === 'error' ? 'bg-red-50 text-red-700 border border-red-200' :
              'bg-blue-50 text-blue-700 border border-blue-200'
            }`}>
              {testStatus === 'testing' && <span className="flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> 正在测试连接...</span>}
              {testStatus === 'success' && <span className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5" /> {testLog}</span>}
              {testStatus === 'error' && <span className="flex items-start gap-2"><XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> <span className="whitespace-pre-wrap">{testLog}</span></span>}
            </div>
          )}
        </div>
        <DialogFooter className="flex items-center justify-between sm:justify-between">
            <Button 
              variant="outline" 
              className="text-blue-600 border-blue-200 hover:bg-blue-50"
              onClick={handleTestConnection}
              disabled={!formData.ip || !formData.username || (!formData.password && !formData.keychain_id) || testStatus === 'testing' || testUnknown}
            >
              测试连接
            </Button>
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
              <Button onClick={() => void handleSubmit()} disabled={!formData.name || !formData.ip || saving || saveUnknown || (!onAddHost && !onEditHost)}>确定</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
