import { Eye, EyeOff } from 'lucide-react';
import React, { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { TerminalCredential } from '@/core/terminal-agent/message-types';

export interface AddCredentialDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAddCredential?: (credential: Omit<TerminalCredential, 'id'> & { value: string }) => void;
}

export function AddCredentialDialog({ open, onOpenChange, onAddCredential }: AddCredentialDialogProps) {
  const [formData, setFormData] = useState({
    name: '',
    type: 'password',
    value: ''
  });
  
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = () => {
    if (onAddCredential) {
      onAddCredential(formData);
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>新建凭证</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <label className="text-sm font-medium">凭证名称</label>
            <Input 
              placeholder="例如：跳板机密码 / 生产环境私钥" 
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">类型</label>
            <Select 
              value={formData.type} 
              onValueChange={(val) => setFormData({ ...formData, type: val, value: '' })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="password">Password (密码)</SelectItem>
                <SelectItem value="ssh_key">SSH Key (私钥)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">{formData.type === 'password' ? '密码' : '私钥内容'}</label>
            {formData.type === 'password' ? (
              <div className="relative mt-1">
                <Input 
                  type={showPassword ? "text" : "password"}
                  placeholder="输入密码" 
                  className="pr-10"
                  value={formData.value}
                  onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 focus:outline-none"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            ) : (
              <Textarea
                placeholder="-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----" 
                value={formData.value}
                onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                className="font-mono text-[11px] h-36 leading-relaxed resize-none p-3 bg-zinc-50 border-zinc-200"
                spellCheck={false}
              />
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSubmit} disabled={!formData.name || !formData.value}>确定</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
