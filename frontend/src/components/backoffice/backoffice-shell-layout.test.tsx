import { render, screen } from "@/test/utils";
import { ShieldCheck } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { BackofficeShellLayout } from "./backoffice-shell-layout";

const mocks = vi.hoisted(() => ({
  usePathname: vi.fn(),
  useRouter: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: mocks.usePathname,
  useRouter: mocks.useRouter,
}));

describe("BackofficeShellLayout", () => {
  it("renders unified sidebar width and main container classes", () => {
    mocks.usePathname.mockReturnValue("/admin");
    mocks.useRouter.mockReturnValue({ replace: vi.fn(), refresh: vi.fn() });

    const navItems = [
      { href: "/admin", label: "总览", icon: ShieldCheck },
      { href: "/admin/users", label: "用户管理", icon: ShieldCheck },
    ];

    render(
      <BackofficeShellLayout
        moduleTitle="平台管理"
        moduleDescription="平台级治理"
        moduleIcon={ShieldCheck}
        navItems={navItems}
        bottomItems={[{ href: "/admin/security", label: "安全与设置", icon: ShieldCheck }]}
      >
        <div>content</div>
      </BackofficeShellLayout>,
    );

    expect(screen.getByText("平台管理")).toBeInTheDocument();
    expect(screen.getByText("平台级治理")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "总览" })).toBeInTheDocument();

    const sidebar = screen.getByText("平台管理").closest("aside");
    expect(sidebar).toHaveClass("w-[240px]");

    const content = screen.getByText("content");
    expect(content.parentElement).toHaveClass("w-full", "px-6", "py-6");
  });
});
