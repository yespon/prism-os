import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { render, screen } from "@/test/utils";

import WorkspaceOverviewPage from "./page";

const mocks = vi.hoisted(() => ({
  useAgents: vi.fn(),
  useAvailableMcpConfig: vi.fn(),
  useMemory: vi.fn(),
  useAvailableModels: vi.fn(),
  useAvailableSkills: vi.fn(),
  useCurrentTenant: vi.fn(),
  useTenantList: vi.fn(),
  useTenantAuditLogs: vi.fn(),
  useSwitchTenant: vi.fn(),
  useThreads: vi.fn(),
}));

vi.mock("@/components/workspace/workspace-container", () => ({
  WorkspaceContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  WorkspaceHeader: () => <div data-testid="workspace-header" />,
  WorkspaceBody: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/core/agents/hooks", () => ({
  useAgents: mocks.useAgents,
}));

vi.mock("@/core/mcp/hooks", () => ({
  useAvailableMcpConfig: mocks.useAvailableMcpConfig,
}));

vi.mock("@/core/memory/hooks", () => ({
  useMemory: mocks.useMemory,
}));

vi.mock("@/core/models/hooks", () => ({
  useAvailableModels: mocks.useAvailableModels,
}));

vi.mock("@/core/skills/hooks", () => ({
  useAvailableSkills: mocks.useAvailableSkills,
}));

vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
  useTenantList: mocks.useTenantList,
  useTenantAuditLogs: mocks.useTenantAuditLogs,
  useSwitchTenant: mocks.useSwitchTenant,
}));

vi.mock("@/core/threads/hooks", () => ({
  useThreads: mocks.useThreads,
}));

describe("WorkspaceOverviewPage", () => {
  it("renders unified overview header and section empty states", () => {
    mocks.useAgents.mockReturnValue({ agents: [] });
    mocks.useAvailableModels.mockReturnValue({ models: [{ enabled: true }] });
    mocks.useAvailableMcpConfig.mockReturnValue({ rawArray: [{ enabled: true }] });
    mocks.useAvailableSkills.mockReturnValue({ skills: [{ enabled: true }] });
    mocks.useMemory.mockReturnValue({ memory: { facts: [] } });
    mocks.useThreads.mockReturnValue({ data: [] });
    mocks.useCurrentTenant.mockReturnValue({ data: { tenant_id: "tenant-a", role: "tenant_admin" } });
    mocks.useTenantList.mockReturnValue({ data: [{ id: "tenant-a", name: "Tenant A" }] });
    mocks.useSwitchTenant.mockReturnValue({ mutate: vi.fn(), isPending: false });
    mocks.useTenantAuditLogs.mockReturnValue({ data: { events: [] } });

    render(<WorkspaceOverviewPage />);

    expect(screen.getByRole("heading", { level: 1, name: "工作台总览" })).toBeInTheDocument();
    expect(screen.getByText("当前工作空间下可直接获取的资源、会话与治理信息")).toBeInTheDocument();
    expect(screen.getByText("我的会话")).toBeInTheDocument();
    expect(screen.getByText("最近会话")).toBeInTheDocument();
    expect(screen.getByText("研发快速入口")).toBeInTheDocument();
    expect(screen.getByText("当前工作空间下暂无会话记录。")).toBeInTheDocument();
  });
});
