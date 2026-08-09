import { Search, Monitor, Plus, ChevronRight, ChevronDown, MoreVertical, TerminalSquare, PanelLeftCloseIcon } from 'lucide-react';
import React, { useState, useEffect } from 'react';

import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import type { TerminalAsset, TerminalAssetGroup, TerminalAssetInput, TerminalCredential } from '@/core/terminal-agent/message-types';

import { AddCredentialDialog } from './add-credential-dialog';
import { AddHostDialog } from './add-host-dialog';

export function AssetSidebar({ 
  onSelectAsset,
  isCollapsed = false,
  onToggleCollapse,
  assets = [],
  credentials = [],
  groups = [],
  onDataChanged,
}: { 
  onSelectAsset: (asset: TerminalAsset) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  assets?: TerminalAsset[];
  credentials?: TerminalCredential[];
  groups?: TerminalAssetGroup[];
  onDataChanged?: () => void;
}) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const [showAddHost, setShowAddHost] = useState(false);
  const [editAsset, setEditAsset] = useState<TerminalAsset | null>(null);
  const [showAddCredential, setShowAddCredential] = useState(false);
  const [search, setSearch] = useState('');

  // Expand all groups by default when groups change
  useEffect(() => {
    const initialExpanded = groups.reduce<Record<string, boolean>>((acc, group) => {
      acc[group.id] = true;
      return acc;
    }, {});
    initialExpanded.ungrouped = true;
    setExpandedGroups(initialExpanded);
  }, [groups]);

  const handleAddHost = async (host: TerminalAssetInput) => {
    try {
      await fetch('/api/v1/assets/local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(host)
      });
      onDataChanged?.();
    } catch (e) {
      console.error(e);
    }
  };

  const handleEditHost = async (id: string, host: TerminalAssetInput) => {
    try {
      await fetch(`/api/v1/assets/local/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(host)
      });
      onDataChanged?.();
      setEditAsset(null);
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteAsset = async (id: string) => {
    if (!confirm('确定要删除该主机吗？')) return;
    try {
      await fetch(`/api/v1/assets/local/${id}`, {
        method: 'DELETE'
      });
      onDataChanged?.();
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddCredential = async (cred: Omit<TerminalCredential, 'id'> & { value: string }) => {
    try {
      await fetch('/api/v1/assets/keychains', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cred)
      });
      onDataChanged?.();
    } catch (e) {
      console.error(e);
    }
  };

  const filteredAssets = assets.filter(a => (a.name ?? '').includes(search) || a.ip.includes(search));

  const toggleGroup = (groupId: string) => {
    setExpandedGroups(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  // Group assets
  const groupedAssets = groups.map(g => ({
    ...g,
    assets: filteredAssets.filter(a => a.group_id === g.id)
  })).filter(g => g.assets.length > 0 || search === '');

  const ungroupedAssets = filteredAssets.filter(a => !a.group_id);

  return (
    <div className={`border-r border-zinc-200 flex flex-col bg-zinc-50/50 shrink-0 transition-all duration-300 ease-in-out overflow-hidden ${
      isCollapsed ? "w-0 border-r-0" : "w-[260px]"
    }`}>
      <div className="w-[260px] h-full flex flex-col">
        <div className="p-4 flex flex-col gap-3 border-b border-transparent">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <h2 className="font-medium text-sm text-zinc-900">主机管理</h2>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-200/50 rounded-md"
                onClick={onToggleCollapse}
                title="折叠主机管理"
              >
                <PanelLeftCloseIcon className="w-3.5 h-3.5" />
              </Button>
            </div>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => {
              setEditAsset(null);
              setShowAddHost(true);
            }}>
              <Plus className="w-4 h-4 text-zinc-500" />
            </Button>
          </div>
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <Input
            placeholder="搜索"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 bg-white border-zinc-200 h-8 text-xs rounded-lg shadow-sm"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-1 mt-2">

        {groupedAssets.map(group => (
          <div key={group.id} className="mb-2">
            <button
              onClick={() => toggleGroup(group.id)}
              className="w-full flex items-center justify-between px-1 mb-1.5 group"
            >
              <span className="text-[11px] font-medium text-zinc-400 group-hover:text-zinc-600 tracking-wider">
                {group.name} <span className="opacity-70 ml-0.5">({group.assets.length})</span>
              </span>
              <div className="text-zinc-300 group-hover:text-zinc-500">
                {expandedGroups[group.id] ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </div>
            </button>
            {expandedGroups[group.id] && (
              <div className="space-y-1">
                {group.assets.map((asset) => (
                  <AssetItem 
                    key={asset.id} 
                    asset={asset} 
                    onSelectAsset={onSelectAsset} 
                    onEditClick={() => {
                      setEditAsset(asset);
                      setShowAddHost(true);
                    }}
                    onDeleteClick={() => handleDeleteAsset(asset.id)}
                  />
                ))}
              </div>
            )}
          </div>
        ))}

        {ungroupedAssets.length > 0 && (
          <div className="mb-2">
              <button
                onClick={() => toggleGroup('ungrouped')}
                className="w-full flex items-center justify-between px-1 mb-1.5 group"
              >
                <span className="text-[11px] font-medium text-zinc-400 group-hover:text-zinc-600 tracking-wider">
                  未分组 <span className="opacity-70 ml-0.5">({ungroupedAssets.length})</span>
                </span>
                <div className="text-zinc-300 group-hover:text-zinc-500">
                  {expandedGroups.ungrouped ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                </div>
              </button>
            {expandedGroups.ungrouped && (
              <div className="space-y-1">
                {ungroupedAssets.map(asset => (
                  <AssetItem 
                    key={asset.id} 
                    asset={asset} 
                    onSelectAsset={onSelectAsset} 
                    onEditClick={() => {
                      setEditAsset(asset);
                      setShowAddHost(true);
                    }}
                    onDeleteClick={() => handleDeleteAsset(asset.id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {filteredAssets.length === 0 && (
          <div className="text-center py-6 text-zinc-400 text-xs">
            暂无主机，点击上方 + 号添加
          </div>
        )}
      </div>

      <AddHostDialog
        open={showAddHost}
        onOpenChange={(val) => {
          setShowAddHost(val);
          if (!val) setEditAsset(null);
        }}
        onAddHost={handleAddHost}
        onEditHost={handleEditHost}
        editAsset={editAsset}
        credentials={credentials}
        groups={groups}
        onAddCredentialClick={() => setShowAddCredential(true)}
      />
      <AddCredentialDialog
        open={showAddCredential}
        onOpenChange={setShowAddCredential}
        onAddCredential={handleAddCredential}
      />
      </div>
    </div>
  );
}

function AssetItem({ 
  asset, 
  onSelectAsset, 
  onEditClick, 
  onDeleteClick 
}: { 
  asset: TerminalAsset;
  onSelectAsset: (a: TerminalAsset) => void;
  onEditClick: () => void;
  onDeleteClick: () => void;
}) {
  return (
    <div className="w-full flex items-center justify-between p-2.5 bg-white border border-zinc-200/80 shadow-sm hover:border-zinc-300 hover:shadow-md rounded-xl group transition-all">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <div className="p-2 bg-blue-50/50 group-hover:bg-blue-50 rounded-lg transition-colors">
          <Monitor className="w-4 h-4 text-blue-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-[13px] text-zinc-900 truncate flex items-center gap-2">
            {asset.name}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5 font-mono truncate">{asset.username}@{asset.ip}</div>
        </div>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-6 w-6 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
            onClick={() => onSelectAsset(asset)}
            title="建立连接"
          >
            <TerminalSquare className="h-3.5 w-3.5" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6 text-zinc-400 hover:bg-zinc-100">
                <MoreVertical className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-32">
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onEditClick(); }}>编辑</DropdownMenuItem>
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDeleteClick(); }} className="text-red-600 focus:text-red-600">删除</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
      </div>
    </div>
  );
}
