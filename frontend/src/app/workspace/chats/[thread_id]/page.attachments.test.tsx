import { describe, expect, it, vi } from "vitest";

import type { UploadedFileInfo } from "@/core/uploads";
import { fireEvent, render, screen, waitFor } from "@/test/utils";

import { ThreadAttachmentsPanel } from "./thread-attachments-panel";

function makeAttachment(overrides: Partial<UploadedFileInfo>): UploadedFileInfo {
  return {
    attachment_id: "att-default",
    filename: "default.txt",
    size: 12,
    path: "/mnt/user-data/uploads/default.txt",
    virtual_path: "/mnt/user-data/uploads/default.txt",
    artifact_url: "/api/threads/thread-1/artifacts/mnt/user-data/uploads/default.txt",
    ...overrides,
  };
}

describe("ThreadAttachmentsPanel", () => {
  it("supports select and unselect attachment", () => {
    const onToggleAttachment = vi.fn();
    const onDeleteAttachment = vi.fn().mockResolvedValue(undefined);
    const onClearSelection = vi.fn();

    const attachments = [
      makeAttachment({
        attachment_id: "att-1",
        filename: "report.pdf",
        content_type: "application/pdf",
      }),
    ];

    render(
      <ThreadAttachmentsPanel
        attachments={attachments}
        selectedAttachmentIds={[]}
        newlyUploadedPreferredIds={[]}
        onToggleAttachment={onToggleAttachment}
        onDeleteAttachment={onDeleteAttachment}
        onClearSelection={onClearSelection}
        onSelectOnlyNewUploads={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("report.pdf"));
    expect(onToggleAttachment).toHaveBeenCalledWith("att-1");
  });

  it("calls delete handler and shows derived/source relation", async () => {
    const onToggleAttachment = vi.fn();
    const onDeleteAttachment = vi.fn().mockResolvedValue(undefined);
    const onClearSelection = vi.fn();
    const onSelectOnlyNewUploads = vi.fn();

    const source = makeAttachment({
      attachment_id: "att-source",
      filename: "slides.pptx",
      content_type:
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      derived_files: [
        {
          attachment_id: "att-md",
          filename: "slides.md",
          virtual_path: "/mnt/user-data/uploads/slides.md",
          artifact_url:
            "/api/threads/thread-1/artifacts/mnt/user-data/uploads/slides.md",
          content_type: "text/markdown",
        },
      ],
    });

    const derived = makeAttachment({
      attachment_id: "att-md",
      filename: "slides.md",
      content_type: "text/markdown",
    });

    render(
      <ThreadAttachmentsPanel
        attachments={[source, derived]}
        selectedAttachmentIds={["att-source", "att-md"]}
        newlyUploadedPreferredIds={["att-md"]}
        onToggleAttachment={onToggleAttachment}
        onDeleteAttachment={onDeleteAttachment}
        onClearSelection={onClearSelection}
        onSelectOnlyNewUploads={onSelectOnlyNewUploads}
      />,
    );

    expect(screen.getByText("转换版 · 来源于 slides.pptx")).toBeInTheDocument();

    const deleteButtons = screen.getAllByText("删除");
    fireEvent.click(deleteButtons[1]!);
    await waitFor(() => {
      expect(onDeleteAttachment).toHaveBeenCalledWith(
        expect.objectContaining({ filename: "slides.md" }),
      );
    });

    fireEvent.click(screen.getByText("清空本轮引用"));
    expect(onClearSelection).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText("仅引用本轮新上传附件"));
    expect(onSelectOnlyNewUploads).toHaveBeenCalledTimes(1);
  });

  it("supports collapse and expand", () => {
    const onToggleAttachment = vi.fn();
    const onDeleteAttachment = vi.fn().mockResolvedValue(undefined);
    const onClearSelection = vi.fn();

    render(
      <ThreadAttachmentsPanel
        attachments={[
          makeAttachment({ attachment_id: "att-1", filename: "a.txt" }),
          makeAttachment({ attachment_id: "att-2", filename: "b.txt" }),
        ]}
        selectedAttachmentIds={["att-1"]}
        newlyUploadedPreferredIds={["att-2"]}
        onToggleAttachment={onToggleAttachment}
        onDeleteAttachment={onDeleteAttachment}
        onClearSelection={onClearSelection}
        onSelectOnlyNewUploads={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("折叠"));
    expect(screen.queryByText("本轮已引用")).not.toBeInTheDocument();
    expect(screen.queryByText("线程历史附件")).not.toBeInTheDocument();
    expect(screen.getByText("展开")).toBeInTheDocument();

    fireEvent.click(screen.getByText("展开"));
    expect(screen.getByText("本轮已引用")).toBeInTheDocument();
    expect(screen.getByText("线程历史附件")).toBeInTheDocument();
  });

  it("shows rename hint when stored filename differs", () => {
    render(
      <ThreadAttachmentsPanel
        attachments={[
          makeAttachment({
            attachment_id: "att-rename",
            filename: "data_1.txt",
            original_filename: "data.txt",
            stored_filename: "data_1.txt",
          }),
        ]}
        selectedAttachmentIds={[]}
        newlyUploadedPreferredIds={[]}
        onToggleAttachment={vi.fn()}
        onDeleteAttachment={vi.fn().mockResolvedValue(undefined)}
        onClearSelection={vi.fn()}
        onSelectOnlyNewUploads={vi.fn()}
      />,
    );

    expect(
      screen.getByText("重命名保存：data.txt → data_1.txt"),
    ).toBeInTheDocument();
  });

  it("shows deleting state and delete failure message", async () => {
    const onDeleteAttachment = vi.fn().mockRejectedValue(new Error("boom"));

    render(
      <ThreadAttachmentsPanel
        attachments={[
          makeAttachment({
            attachment_id: "att-fail",
            filename: "fail.txt",
          }),
        ]}
        selectedAttachmentIds={[]}
        newlyUploadedPreferredIds={[]}
        onToggleAttachment={vi.fn()}
        onDeleteAttachment={onDeleteAttachment}
        onClearSelection={vi.fn()}
        onSelectOnlyNewUploads={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("删除"));
    expect(screen.getByText("删除中...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("删除失败：fail.txt")).toBeInTheDocument();
    });
  });
});
