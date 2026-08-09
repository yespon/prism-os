import { describe, expect, it, vi } from "vitest";

import { render, screen } from "@/test/utils";

import SetupPage from "./page";

const mocks = vi.hoisted(() => ({
  fetchAuthApi: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  login: vi.fn(),
}));

vi.mock("@/core/api/auth-client", () => ({
  fetchAuthApi: mocks.fetchAuthApi,
}));

vi.mock("@/core/auth/auth-api", () => ({
  login: mocks.login,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mocks.replace,
    refresh: mocks.refresh,
  }),
}));

describe("SetupPage", () => {
  it("shows a visible error when bootstrap status cannot be loaded", async () => {
    mocks.fetchAuthApi.mockImplementation(() =>
      Promise.reject(new Error("gateway unavailable")),
    );

    render(<SetupPage />);

    expect(await screen.findByText("无法检查系统状态")).toBeInTheDocument();
  });
});
