"use client";

import { Bot, Plus, SearchIcon, Loader2, Upload, Trash2, Edit3 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, useRef } from "react";
import { toast } from "sonner";

import { SkillImportOperations } from "@/components/workspace/skills/skill-import-operations";
import { skillImportErrorMessage } from "@/core/skills/imports";
import { useSkillImportContext } from "@/core/skills/import-context";
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/core/auth/hooks";
import { useI18n } from "@/core/i18n/hooks";
import { isPlatformAdminRole } from "@/core/permissions/roles";
import { useAvailableSkills, useCreatePersonalSkill, useImportPersonalSkill, useDeletePersonalSkill } from "@/core/skills/hooks";
import type { AvailableSkillResponse } from "@/core/skills/type";

export default function SkillsCenterPage() {
  const { t, locale } = useI18n();
  const importContext = useSkillImportContext();
  const importIdentity = useRef(importContext.key);
  importIdentity.current = importContext.key;
  const archiveBusy = useRef(false);
  const archiveGeneration = useRef(0);
  const changeArchiveOpen = (value: boolean) => { archiveGeneration.current += 1; archiveBusy.current = false; setImportOpen(value); };
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlFilter = searchParams.get("filter");
  const { data: session } = useSession();
  const { skills, isLoading, error } = useAvailableSkills();
  const [searchTerm, setSearchTerm] = useState("");
  const [filter, setFilter] = useState<"all" | "personal" | "tenant" | "global">(
    (urlFilter === "personal" || urlFilter === "tenant" || urlFilter === "global") ? urlFilter : "all"
  );

  // Create/Import Skill state
  const [operationsOpen, setOperationsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [archiveFile, setArchiveFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => { setImportOpen(false); setArchiveFile(null); archiveBusy.current = false; }, [importContext.key]);

  const { mutateAsync: createPersonalSkill, isPending: isCreating } = useCreatePersonalSkill();
  const { mutateAsync: importPersonalSkill, isPending: isImporting } = useImportPersonalSkill();
  const { mutateAsync: deletePersonalSkill, isPending: isDeleting } = useDeletePersonalSkill();

  const [deletingSkill, setDeletingSkill] = useState<string | null>(null);

  const isAdmin = isPlatformAdminRole(session?.user?.role) || session?.user?.role === "tenant_admin";

  const filteredSkills = useMemo(() => {
    return skills.filter((s) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "personal" && s.scope === "personal") ||
        (filter === "tenant" && s.scope === "tenant") ||
        (filter === "global" && s.scope === "global");
      const matchesSearch =
        searchTerm === "" ||
        s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (s.description || "").toLowerCase().includes(searchTerm.toLowerCase());
      return matchesFilter && matchesSearch;
    });
  }, [skills, searchTerm, filter]);


  const handleArchiveSelect = (file: File | null) => {
    if (!file) {
      setArchiveFile(null);
      return;
    }
    if (file.name.endsWith(".skill") || file.name.endsWith(".zip")) {
      setArchiveFile(file);
      return;
    }
    setArchiveFile(null);
    toast.error("只支持 .skill 或 .zip 格式");
  };

  const openArchivePicker = () => {
    fileInputRef.current?.click();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    handleArchiveSelect(e.dataTransfer.files?.[0] ?? null);
  };

  const handleImport = async () => {
    if (!importContext.identityReady || !importContext.isCurrent() || archiveBusy.current) return;
    const identity = importContext.key;
    const generation = archiveGeneration.current;
    const current = () => archiveGeneration.current === generation && importIdentity.current === identity && importContext.isCurrent();
    archiveBusy.current = true;
    try {
      if (!archiveFile) {
        toast.error("请选择要导入的技能包文件");
        return;
      }
      await importPersonalSkill(archiveFile);
      if (!current()) return;
      toast.success("导入成功");
      setImportOpen(false);
    } catch (err) {
      if (current()) toast.error(skillImportErrorMessage(err, locale === "zh-CN"));
    } finally {
      if (current()) archiveBusy.current = false;
    }
  };

  const handleOpenImport = () => {
    setArchiveFile(null);
    changeArchiveOpen(true);
  };

  const handleDelete = async (skillName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定要删除私有 Skill "${skillName}" 吗？此操作不可恢复。`)) return;
    setDeletingSkill(skillName);
    try {
      await deletePersonalSkill(skillName);
      toast.success(`已删除 ${skillName}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeletingSkill(null);
    }
  };

  return (
    <div className="flex size-full flex-col bg-zinc-50/50 dark:bg-zinc-950/20 overflow-hidden p-6 gap-4 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex shrink-0 items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{(t.sidebarNav as Record<string, string>).skillsPlaza ?? 'Skills Plaza'}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            浏览和使用前人沉淀的诊断 SOP，或分享你提炼的经验
          </p>
        </div>
      </div>

      {/* Search & Filter */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="relative w-80">
          <SearchIcon className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜索 Skill..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9"
          />
        </div>
        <Tabs value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
          <TabsList>
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="personal">我的 Skill</TabsTrigger>
            <TabsTrigger value="tenant">团队 Skill</TabsTrigger>
            <TabsTrigger value="global">内置</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" onClick={handleOpenImport}>
            <Upload className="mr-2 h-4 w-4" />
            导入 Skill
          </Button>
          <Button onClick={() => router.push("/workspace/skills/new")}>
            <Plus className="mr-2 h-4 w-4" />
            新建私有 Skill
          </Button>
          {isAdmin && (
            <Button variant="outline" onClick={() => router.push("/tenant-admin/skills")}>
              管理后台
            </Button>
          )}
        </div>
      </div>

      <details className="shrink-0" onToggle={event => setOperationsOpen(event.currentTarget.open)}>
        <summary>{locale === "zh-CN" ? "Skill 导入记录与恢复" : "Skill import records and recovery"}</summary>
        {operationsOpen && <SkillImportOperations scope="personal" locale={locale === "zh-CN" ? "zh" : "en"} />}
      </details>

      {/* Skill Grid */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="flex h-64 items-center justify-center text-destructive">
            加载失败：{error.message}
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-muted-foreground">
            <Bot className="h-10 w-10 opacity-30" />
            <p>暂无 Skill</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filteredSkills.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onClick={() => router.push(`/workspace/skills/${skill.name}`)}
                onDelete={skill.scope === "personal" ? (e: React.MouseEvent) => handleDelete(skill.name, e) : undefined}
                isDeleting={deletingSkill === skill.name}
              />
            ))}
          </div>
        )}
      </div>

      <Dialog open={importOpen} onOpenChange={changeArchiveOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>导入私有 Skill</DialogTitle>
            <DialogDescription>
              选择本地的 .skill 或 .zip 压缩包导入
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 py-4">
            <input
              ref={fileInputRef}
              type="file"
              aria-label={t.tenantAdmin.skills.importFileLabel}
              accept=".skill,.zip,application/zip"
              className="hidden"
              onChange={(e) => {
                handleArchiveSelect(e.target.files?.[0] ?? null);
                e.currentTarget.value = "";
              }}
            />
            <div
              className={`cursor-pointer rounded-lg border-2 border-dashed p-8 transition-colors ${
                isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25"
              }`}
              role="button"
              tabIndex={0}
              onClick={openArchivePicker}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  openArchivePicker();
                }
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                setIsDragging(false);
              }}
              onDrop={handleDrop}
            >
              <div className="flex flex-col items-center justify-center gap-4 text-center">
                <div className="rounded-full bg-muted p-3">
                  <Upload className="h-6 w-6 text-muted-foreground" />
                </div>
                <div>
                  <div className="text-sm font-medium">{t.tenantAdmin.skills.importFileLabel}</div>
                  <p className="mt-1 text-sm text-muted-foreground">{t.tenantAdmin.skills.importFileHint}</p>
                </div>
                <div className="flex flex-col items-center gap-2">
                  <Button type="button" variant="outline" onClick={(e) => {
                    e.stopPropagation();
                    openArchivePicker();
                  }}>
                    {t.tenantAdmin.skills.importFileLabel}
                  </Button>
                  {archiveFile && (
                    <span className="text-sm font-medium text-primary">{archiveFile.name}</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => changeArchiveOpen(false)}>
              {t.common.cancel}
            </Button>
            <Button 
              onClick={handleImport} 
              disabled={isImporting || !archiveFile}
            >
              {isImporting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t.tenantAdmin.skills.import}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SkillCard({
  skill,
  onClick,
  onDelete,
  isDeleting,
}: {
  skill: AvailableSkillResponse;
  onClick: () => void;
  onDelete?: (e: React.MouseEvent) => void;
  isDeleting?: boolean;
}) {
  const canEdit = skill.managed_by_current_user && skill.scope !== "global";

  return (
    <div
      className="group relative rounded-xl border bg-card p-5 shadow-sm transition-all duration-200 hover:shadow-md"
    >
      {/* Action buttons for editable skills */}
      <div className="absolute top-3 right-3 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {canEdit && (
          <button
            onClick={onClick}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-primary hover:bg-primary/10 transition-colors"
            title="编辑此 Skill"
          >
            <Edit3 className="h-3.5 w-3.5" />
          </button>
        )}
        {onDelete && (
          <button
            onClick={onDelete}
            disabled={isDeleting}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
            title="删除此 Skill"
          >
            {isDeleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </button>
        )}
      </div>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-sm truncate">{skill.name}</h3>
            {skill.scope === "global" && (
              <span className="shrink-0 rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] text-blue-700 dark:text-blue-400">
                内置
              </span>
            )}
            {skill.scope === "tenant" && (
              <span className="shrink-0 rounded-full bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-700 dark:text-purple-400">
                团队共享
              </span>
            )}
            {skill.scope === "personal" && (
              <span className="shrink-0 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-700 dark:text-emerald-400">
                私有
              </span>
            )}
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground line-clamp-2">
            {skill.description || "暂无描述"}
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3 text-[10px] text-muted-foreground">
        {skill.bound_tools && skill.bound_tools.length > 0 && (
          <span>🔧 {skill.bound_tools.length} 个工具</span>
        )}
        {skill.version !== undefined && skill.version > 0 && (
          <span>v{skill.version}</span>
        )}
        <span className={skill.enabled !== false ? "text-green-600" : "text-muted-foreground"}>
          {skill.enabled !== false ? "● 已启用" : "○ 已禁用"}
        </span>
      </div>
    </div>
  );
}
