import { render, screen } from "@/test/utils";
import { describe, expect, it, vi } from "vitest";

import AdminDashboardPage from "./page";

const mocks = vi.hoisted(() => ({
  useQuery: vi.fn(),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQuery: mocks.useQuery,
}));

describe("AdminDashboardPage", () => {
  it("renders unified overview header, KPI blocks and empty audit state", () => {
    mocks.useQuery.mockImplementation(({ queryKey }: { queryKey: string[] }) => {
      if (queryKey[0] === "admin_overview") {
        return {
          data: {
            total_users: 12,
            active_users: 10,
            suspended_users: 2,
            total_threads: 88,
            total_files: 233,
            total_bytes: 1024,
            total_tenants: 4,
            active_tenants: 3,
            platform_model_template_count: 6,
            assigned_model_count: 9,
            bootstrap_admin_users: 1,
            must_change_password_users: 2,
            recent_new_users_7d: 5,
          },
        };
      }
      return { data: { events: [] } };
    });

    render(<AdminDashboardPage />);

    expect(screen.getByRole("heading", { level: 1, name: "总览" })).toBeInTheDocument();
    expect(screen.getByText("平台治理核心指标与全局运行统计")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看审计日志" })).toBeInTheDocument();

    expect(screen.getByText("总用户数")).toBeInTheDocument();
    expect(screen.getByText("总线程数")).toBeInTheDocument();
    expect(screen.getByText("工作空间总数")).toBeInTheDocument();
    expect(screen.getByText("平台模型模板数")).toBeInTheDocument();
    expect(screen.getByText("最近审计记录")).toBeInTheDocument();
    expect(screen.getByText("暂无记录")).toBeInTheDocument();
  });
});
