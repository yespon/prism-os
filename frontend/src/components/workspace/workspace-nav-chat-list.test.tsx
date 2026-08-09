import { render, screen } from "@/test/utils";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { WorkspaceNavChatList } from "./workspace-nav-chat-list";

const mocks = vi.hoisted(() => ({
  usePathname: vi.fn(),
  useSession: vi.fn(),
  useActiveAnnouncements: vi.fn(),
  useI18n: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: mocks.usePathname,
}));

vi.mock("@/core/auth/hooks", () => ({
  useSession: mocks.useSession,
}));

vi.mock("@/core/announcements", () => ({
  useActiveAnnouncements: mocks.useActiveAnnouncements,
}));

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: mocks.useI18n,
}));

const t = {
  sidebarNav: {
    overview: "总览",
    smartWorkbench: "智能工作台",
    agents: "智能体",
    announcements: "平台通知",
    auditGovernance: "审计治理",
    systemSettings: "系统设置",
  },
};

describe("WorkspaceNavChatList", () => {
  beforeEach(() => {
    mocks.useActiveAnnouncements.mockReturnValue({ announcements: [] });
    mocks.useI18n.mockReturnValue({ t });
  });

  it("points intelligent workspace entry to valid chats route", () => {
    mocks.usePathname.mockReturnValue("/workspace/overview");
    mocks.useSession.mockReturnValue({ data: { user: { role: "user" } } });

    render(<WorkspaceNavChatList />);

    expect(screen.getByRole("link", { name: "智能工作台" })).toHaveAttribute(
      "href",
      "/workspace/chats/new",
    );
  });

  it("shows unread announcement badge on announcements nav item", () => {
    mocks.usePathname.mockReturnValue("/workspace/overview");
    mocks.useSession.mockReturnValue({ data: { user: { role: "user" } } });
    mocks.useActiveAnnouncements.mockReturnValue({
      announcements: [
        { id: 1, read_state: { is_read: false } },
        { id: 2, read_state: { is_read: false } },
        { id: 3, read_state: { is_read: true } },
      ],
    });

    render(<WorkspaceNavChatList />);

    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
