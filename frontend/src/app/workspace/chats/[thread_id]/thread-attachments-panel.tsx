import { useState } from "react";

import { getAuthToken } from "@/core/auth/auth-api";
import { getBackendBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import type { UploadedFileInfo } from "@/core/uploads";
import { cn } from "@/lib/utils";

export function ThreadAttachmentsPanel({
  attachments,
  selectedAttachmentIds,
  newlyUploadedPreferredIds,
  onToggleAttachment,
  onDeleteAttachment,
  onClearSelection,
  onSelectOnlyNewUploads,
}: {
  attachments: UploadedFileInfo[];
  selectedAttachmentIds: string[];
  newlyUploadedPreferredIds: string[];
  onToggleAttachment: (attachmentId: string) => void;
  onDeleteAttachment: (file: UploadedFileInfo) => Promise<void>;
  onClearSelection: () => void;
  onSelectOnlyNewUploads: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const { t } = useI18n();

  if (attachments.length === 0) {
    return null;
  }

  const formatSize = (size: number | string | undefined) => {
    const bytes = Number(size ?? 0);
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return "0 B";
    }
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    if (bytes < 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const derivedMap = new Map<string, string>();
  for (const source of attachments) {
    for (const derived of source.derived_files ?? []) {
      if (derived.attachment_id && source.filename) {
        derivedMap.set(derived.attachment_id, source.filename);
      }
    }
  }

  const selectedSet = new Set(selectedAttachmentIds);
  const selectedAttachments = attachments.filter((file) => {
    const normalizedId = file.attachment_id ?? `legacy:${file.filename}`;
    return selectedSet.has(normalizedId);
  });
  const historyAttachments = attachments.filter((file) => {
    const normalizedId = file.attachment_id ?? `legacy:${file.filename}`;
    return !selectedSet.has(normalizedId);
  });

  const renderAttachment = (file: UploadedFileInfo) => {
    const normalizedId = file.attachment_id ?? `legacy:${file.filename}`;
    const checked = selectedAttachmentIds.includes(normalizedId);
    const deleting = deletingIds.has(normalizedId);
    const derivedFrom = file.attachment_id
      ? derivedMap.get(file.attachment_id)
      : undefined;
    const isDerived = Boolean(derivedFrom);
    const fileType = file.content_type ?? file.extension ?? "unknown";
    const sizeText = formatSize(file.size);
    const originalFilename = file.original_filename ?? file.filename;
    const storedFilename = file.stored_filename ?? file.filename;
    const renamed = originalFilename !== storedFilename;
    const artifactHref =
      typeof file.artifact_url === "string" && file.artifact_url.startsWith("/")
        ? `${getBackendBaseURL()}${file.artifact_url}`
        : file.artifact_url;

    const openArtifactWithAuth = async () => {
      try {
        const token = getAuthToken();
        const url = new URL(artifactHref, window.location.origin);
        if (token && !url.searchParams.get("token")) {
          url.searchParams.set("token", token);
        }
        window.open(url.toString(), "_blank", "noopener,noreferrer");
      } catch {
        window.open(artifactHref, "_blank", "noopener,noreferrer");
      }
    };

    return (
      <div
        key={normalizedId}
        className={cn(
          "rounded-2xl border px-3 py-2 shadow-sm transition-colors",
          checked ? "border-primary bg-primary/8" : "border-border bg-background",
        )}
      >
        <div className="flex items-start gap-2">
          <button
            type="button"
            className={cn(
              "min-w-0 flex-1 text-left",
              checked ? "text-primary" : "text-foreground",
            )}
            aria-pressed={checked}
            onClick={() => onToggleAttachment(normalizedId)}
          >
            <span className="block truncate text-sm font-medium">{file.filename}</span>
          </button>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground text-xs"
              onClick={() => {
                void openArtifactWithAuth();
              }}
            >
              {t.attachments.open}
            </button>
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive text-xs"
              disabled={deleting}
              onClick={() => {
                setDeleteError(null);
                setDeletingIds((previous) => new Set(previous).add(normalizedId));
                void onDeleteAttachment(file)
                  .catch(() => {
                    setDeleteError(t.attachments.deleteFailed(file.filename));
                  })
                  .finally(() => {
                    setDeletingIds((previous) => {
                      const next = new Set(previous);
                      next.delete(normalizedId);
                      return next;
                    });
                  });
              }}
            >
              {deleting ? t.attachments.deleting : t.attachments.delete}
            </button>
          </div>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
          <span className="rounded-full bg-muted px-2 py-0.5">{fileType}</span>
          <span className="rounded-full bg-muted px-2 py-0.5">{sizeText}</span>
          {isDerived && (
            <span className="rounded-full bg-muted px-2 py-0.5">
              {t.attachments.convertedFrom(derivedFrom ?? "unknown")}
            </span>
          )}
          {renamed && (
            <span className="rounded-full bg-muted px-2 py-0.5">
              {t.attachments.renamed(originalFilename, storedFilename)}
            </span>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="mb-2 rounded-2xl border bg-background/85 p-3 shadow-sm backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="text-sm font-medium">{t.attachments.title}</div>
          <span className="text-[11px] text-muted-foreground">
            {selectedAttachments.length > 0 && t.attachments.referencedCount(selectedAttachments.length)}
            {historyAttachments.length > 0 && `${selectedAttachments.length > 0 ? ', ' : ''}${t.attachments.historyCount(historyAttachments.length)}`}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setCollapsed((previous) => !previous)}
          >
            {collapsed ? t.attachments.expand : t.attachments.collapse}
          </button>
          {!collapsed && (
            <>
              <div className="text-muted-foreground text-xs">{t.attachments.currentRoundSelectable}</div>
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground"
                onClick={onClearSelection}
                disabled={selectedAttachmentIds.length === 0}
              >
                {t.attachments.clearCurrentRound}
              </button>
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground"
                onClick={onSelectOnlyNewUploads}
                disabled={newlyUploadedPreferredIds.length === 0}
              >
                {t.attachments.onlyNewUploads}
              </button>
            </>
          )}
        </div>
      </div>
      {!collapsed && (
        <>
          <div className="mt-2 text-[11px] text-muted-foreground">
            {t.attachments.uploadHint}
            {newlyUploadedPreferredIds.length > 0
              ? ` ${t.attachments.identifiedFiles(newlyUploadedPreferredIds.length)}`
              : ` ${t.attachments.noIdentifiedFiles}`}
          </div>
          {deleteError && (
            <div className="mt-2 text-[11px] text-destructive">{deleteError}</div>
          )}
          <div className="mt-3 space-y-3">
            <section>
              <div className="mb-2 text-xs font-medium text-foreground/85">{t.attachments.currentRoundReferenced}</div>
              {selectedAttachments.length === 0 ? (
                <div className="text-xs text-muted-foreground">{t.attachments.noAttachments}</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {selectedAttachments.map(renderAttachment)}
                </div>
              )}
            </section>

            <section>
              <div className="mb-2 text-xs font-medium text-foreground/85">{t.attachments.historyAttachments}</div>
              {historyAttachments.length === 0 ? (
                <div className="text-xs text-muted-foreground">{t.attachments.noReusableAttachments}</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {historyAttachments.map(renderAttachment)}
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
