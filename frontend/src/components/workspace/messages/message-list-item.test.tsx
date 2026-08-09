import type { Message } from "@langchain/langgraph-sdk";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { fireEvent, render, screen } from "@/test/utils";

const mocks = vi.hoisted(() => ({
  useParams: vi.fn(),
  useArtifactAccessToken: vi.fn(),
  useI18n: vi.fn(),
  useRehypeSplitWordsIntoSpans: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: mocks.useParams,
}));

vi.mock("@/core/artifacts/hooks", () => ({
  useArtifactAccessToken: mocks.useArtifactAccessToken,
}));

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: mocks.useI18n,
}));

vi.mock("@/core/rehype", () => ({
  useRehypeSplitWordsIntoSpans: mocks.useRehypeSplitWordsIntoSpans,
  rehypeSplitWordsIntoSpans: vi.fn(),
}));

vi.mock("@/core/streamdown", () => ({
  humanMessagePlugins: {
    remarkPlugins: [],
    rehypePlugins: [],
  },
}));

vi.mock("./markdown-content", () => ({
  MarkdownContent: ({ content }: { content: string }) => (
    <div data-testid="markdown-content">{content}</div>
  ),
}));

vi.mock("../copy-button", () => ({
  CopyButton: () => null,
}));

vi.mock("@/components/ai-elements/message", () => ({
  Message: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  MessageContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  MessageResponse: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  MessageToolbar: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ai-elements/reasoning", () => ({
  Reasoning: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ReasoningContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ReasoningTrigger: () => <div />,
}));

vi.mock("@/components/ai-elements/task", () => ({
  Task: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TaskTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ai-elements/loader", () => ({
  Loader: () => <div />,
}));

import { MessageListItem } from "./message-list-item";

describe("MessageListItem", () => {
  it("renders structured attachments from additional_kwargs.attachments", () => {
    mocks.useParams.mockReturnValue({ thread_id: "thread-1" });
    mocks.useArtifactAccessToken.mockReturnValue("session-token");
    mocks.useI18n.mockReturnValue({
      t: {
        uploads: { uploading: "上传中" },
        messageGroup: { retryInstruction: "重试此指令" },
        clipboard: {
          copyToClipboard: "复制",
          copiedToClipboard: "已复制",
          failedToCopyToClipboard: "复制失败",
        },
      },
    });
    mocks.useRehypeSplitWordsIntoSpans.mockReturnValue([]);

    const message = {
      type: "human",
      id: "msg-1",
      content: "请查看附件",
      additional_kwargs: {
        attachments: [
          {
            attachment_id: "att-1",
            filename: "report.pdf",
            virtual_path: "/mnt/user-data/uploads/report.pdf",
            artifact_url:
              "/api/threads/thread-1/artifacts/mnt/user-data/uploads/report.pdf",
            size: 1024,
          },
        ],
      },
    } as Message;

    render(
      <MessageListItem
        message={message}
        availableAttachmentKeys={new Set(["att-1"])}
      />,
    );

    const link = screen.getByRole("link", { name: "report.pdf" });
    expect(link.getAttribute("href")).toContain("token=session-token");
  });

  it("retries the original human message object", () => {
    mocks.useParams.mockReturnValue({ thread_id: "thread-1" });
    mocks.useArtifactAccessToken.mockReturnValue("session-token");
    mocks.useI18n.mockReturnValue({
      t: {
        uploads: { uploading: "上传中" },
        messageGroup: { retryInstruction: "重试此指令" },
        clipboard: {
          copyToClipboard: "复制",
          copiedToClipboard: "已复制",
          failedToCopyToClipboard: "复制失败",
        },
      },
    });
    mocks.useRehypeSplitWordsIntoSpans.mockReturnValue([]);

    const message = {
      type: "human",
      id: "msg-2",
      content: "请查看附件",
      additional_kwargs: {
        attachments: [
          {
            attachment_id: "att-2",
            filename: "summary.md",
            virtual_path: "/mnt/user-data/uploads/summary.md",
            artifact_url:
              "/api/threads/thread-1/artifacts/mnt/user-data/uploads/summary.md",
            size: 2048,
          },
        ],
      },
    } as Message;

    const onRetry = vi.fn();

    render(
      <MessageListItem
        message={message}
        availableAttachmentKeys={new Set(["att-2"])}
        onRetry={onRetry}
      />,
    );

    fireEvent.click(screen.getByRole("button"));
    expect(onRetry).toHaveBeenCalledWith(message);
  });
});
