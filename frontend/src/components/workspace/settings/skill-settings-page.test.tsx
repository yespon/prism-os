import { beforeEach, expect, it, vi } from "vitest";

import { SkillMutationError } from "@/core/skills/mutations";
import { fireEvent, render, screen } from "@/test/utils";

import { SkillSettingsPage } from "./skill-settings-page";

const mock = vi.hoisted(() => ({
  key: "tenant-a/user-a",
  current: true,
  toggle: vi.fn(),
  inspect: vi.fn(),
  error: vi.fn(),
  blocked: false,
  skills: [] as Record<string, unknown>[],
}));
vi.mock("@/core/skills/import-context", () => ({
  useSkillImportContext: () => ({
    key: mock.key,
    isCurrent: () => mock.current,
  }),
}));
vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: () => ({ data: { role: "tenant_admin" } }),
}));
vi.mock("@/core/skills/hooks", () => ({
  useAvailableSkills: () => ({ skills: mock.skills, isLoading: false }),
  useUpdateTenantSkill: () => ({
    mutate: mock.toggle,
    canToggleResource: () => !mock.blocked,
    enablementNeedsInspection: mock.blocked,
    inspectEnablement: mock.inspect,
  }),
}));
vi.mock("sonner", () => ({ toast: { error: mock.error } }));
vi.mock("@/env", () => ({ env: { NEXT_PUBLIC_STATIC_WEBSITE_ONLY: "false" } }));
beforeEach(() => {
  vi.clearAllMocks();
  mock.key = "tenant-a/user-a";
  mock.current = true;
  mock.blocked = false;
  mock.skills = [
    {
      name: "collision",
      description: "Public source",
      category: "public",
      scope: "global",
      resource_id: "public:current",
      enabled: true,
      managed_by_current_user: true,
    },
    {
      name: "collision",
      description: "Shared source",
      category: "custom",
      scope: "tenant",
      resource_id: "skill:shared",
      enabled: true,
      managed_by_current_user: true,
    },
    {
      name: "collision",
      description: "Personal source",
      category: "custom",
      scope: "personal",
      resource_id: "skill:personal",
      enabled: true,
      managed_by_current_user: true,
    },
  ];
});
function customTab() {
  const tab = screen.getByRole("tab", { name: "自定义" });
  fireEvent.pointerDown(tab);
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}
it("allows a tenant administrator to toggle the selected public source", () => {
  render(<SkillSettingsPage />);
  const toggle = screen.getByRole("switch");
  expect(toggle).toBeEnabled();
  fireEvent.click(toggle);
  expect(mock.toggle).toHaveBeenCalledWith(
    {
      skillName: "collision",
      enabled: false,
      expectedResourceId: "public:current",
    },
    expect.any(Object),
  );
});
it("keeps same-name shared and personal resources visible without routing personal to shared enablement", () => {
  render(<SkillSettingsPage />);
  customTab();
  expect(screen.getByText("Shared source")).toBeInTheDocument();
  expect(screen.getByText("Personal source")).toBeInTheDocument();
  const toggles = screen.getAllByRole("switch");
  expect(toggles[0]).toBeEnabled();
  expect(toggles[1]).toBeDisabled();
  fireEvent.click(toggles[0]!);
  expect(mock.toggle).toHaveBeenCalledWith(
    {
      skillName: "collision",
      enabled: false,
      expectedResourceId: "skill:shared",
    },
    expect.any(Object),
  );
});
it("shows an explicit inspection action while repeated enablement is blocked", () => {
  mock.blocked = true;
  mock.inspect.mockResolvedValueOnce(undefined);
  render(<SkillSettingsPage />);
  expect(screen.getByRole("switch")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新检查启停状态" }));
  expect(mock.inspect).toHaveBeenCalledOnce();
});
it("does not show an old identity toggle error in the new settings view", () => {
  const view = render(<SkillSettingsPage />);
  fireEvent.click(screen.getByRole("switch"));
  const callback = mock.toggle.mock.calls[0]?.[1] as {
    onError: (error: Error) => void;
  };
  mock.key = "tenant-b/user-b";
  view.rerender(<SkillSettingsPage />);
  callback.onError(new SkillMutationError(503, "public:current", true));
  expect(mock.error).not.toHaveBeenCalled();
});
