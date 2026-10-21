import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AssetOperationError } from "@/core/terminal-agent/assets-api";

import { AddCredentialDialog } from "./add-credential-dialog";
import { AddHostDialog } from "./add-host-dialog";
import { PersistentTerminal } from "./persistent-terminal";

const scope = vi.hoisted(() => ({ key: "current" }));
vi.mock("@/core/skills/query-identity", () => ({
  useSkillQueryIdentity: () => {
    const key = scope.key;
    return { key, identityReady: true, isCurrent: () => scope.key === key };
  },
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/workspace/terminal", useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("@/app/workspace/terminal/terminal-agent-ui", () => ({ TerminalAgentUI: () => null }));
vi.mock("./web-terminal", () => ({ WebTerminal: () => <span data-testid="owned-terminal">Transport</span> }));
vi.mock("./asset-sidebar", () => ({ AssetSidebar: ({ assets, onSelectAsset, onDataChanged }: {
  assets: { id: string; name: string }[]; onSelectAsset: (asset: unknown) => void; onDataChanged: () => void;
}) => <div><button onClick={onDataChanged}>Refresh assets</button>{assets.map(asset => <button key={asset.id} onClick={() => onSelectAsset(asset)}>{asset.name}</button>)}</div> }));
vi.mock("@/components/ui/resizable-panel", () => ({ ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
beforeEach(() => { scope.key = "current"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function enterCredential() {
  fireEvent.change(screen.getByPlaceholderText("例如：跳板机密码 / 生产环境私钥"), { target: { value: "Owned" } });
  fireEvent.change(screen.getByPlaceholderText("输入密码"), { target: { value: "synthetic-only" } });
}

it("keeps the credential dialog open until persistence is confirmed and dispatches once", async () => {
  let finish!: () => void;
  const save = vi.fn().mockImplementation(() => new Promise<void>(resolve => { finish = resolve; }));
  const close = vi.fn();
  render(<AddCredentialDialog open onOpenChange={close} onAddCredential={save} />);
  enterCredential();
  fireEvent.click(screen.getByRole("button", { name: "确定" }));
  expect(save).toHaveBeenCalledTimes(1);
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "保存中…" })).toBeDisabled();
  await act(async () => finish());
  await waitFor(() => expect(close).toHaveBeenCalledWith(false));
});

it("keeps rejected credential input and never closes as if saved", async () => {
  const close = vi.fn();
  const save = vi.fn().mockRejectedValue(new AssetOperationError("当前权限已失效"));
  render(<AddCredentialDialog open onOpenChange={close} onAddCredential={save} />);
  enterCredential();
  fireEvent.click(screen.getByRole("button", { name: "确定" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("当前权限已失效");
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByPlaceholderText("输入密码")).toHaveValue("synthetic-only");
});

it("blocks replay of unknown credential outcomes across closing and reopening", async () => {
  const close = vi.fn();
  const save = vi.fn().mockRejectedValue(new AssetOperationError("请先核对", true));
  const view = render(<AddCredentialDialog open onOpenChange={close} onAddCredential={save} />);
  enterCredential();
  fireEvent.click(screen.getByRole("button", { name: "确定" }));
  await screen.findByRole("alert");
  view.rerender(<AddCredentialDialog open={false} onOpenChange={close} onAddCredential={save} />);
  view.rerender(<AddCredentialDialog open onOpenChange={close} onAddCredential={save} />);
  expect(screen.getByRole("button", { name: "确定" })).toBeDisabled();
  expect(save).toHaveBeenCalledTimes(1);
});

it("allows an existing owned credential without an inline password and reports unknown connection", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { inspection_required: true } }), { status: 503 }));
  vi.stubGlobal("fetch", fetch);
  const close = vi.fn();
  const save = vi.fn();
  render(<AddHostDialog open onOpenChange={close} onEditHost={save}
    editAsset={{ id: "owned-host", name: "Owned", ip: "127.0.0.1", port: 22, username: "owned", keychain_id: "credential", group_id: null }}
    credentials={[{ id: "credential", name: "Owned credential", type: "password" }]} />);
  const test = screen.getByRole("button", { name: "测试连接" });
  expect(test).not.toBeDisabled();
  fireEvent.click(test);
  await waitFor(() => expect(test).toBeDisabled());
  await screen.findByText(/操作结果未确认/);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(close).not.toHaveBeenCalled();
});

it("discards late private asset lists after an identity switch", async () => {
  const old: ((response: Response) => void)[] = [];
  let calls = 0;
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async (path: string) => {
    calls += 1;
    if (calls <= 3) return new Promise<Response>(resolve => old.push(resolve));
    return new Response(JSON.stringify(path.endsWith("/local") ? [{ id: "new", name: "Current B", ip: "127.0.0.1" }] : []));
  }));
  const view = render(<PersistentTerminal />);
  await waitFor(() => expect(old).toHaveLength(3));
  scope.key = "changed";
  view.rerender(<PersistentTerminal />);
  await screen.findByText("Current B");
  await act(async () => { old.forEach((resolve, i) => resolve(new Response(JSON.stringify(i === 0 ? [{ id: "old", name: "Private A", ip: "127.0.0.1" }] : [])))); });
  expect(screen.queryByText("Private A")).not.toBeInTheDocument();
  expect(screen.getByText("Current B")).toBeInTheDocument();
});

it("clears cached assets and closes their transport when current list access is refused", async () => {
  let refused = false;
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async (path: string) => new Response(
    JSON.stringify(refused ? { detail: "withdrawn" } : path.endsWith("/local") ? [{ id: "owned", name: "Owned asset", ip: "127.0.0.1" }] : []),
    { status: refused ? 403 : 200 },
  )));
  render(<PersistentTerminal />);
  fireEvent.click(await screen.findByText("Owned asset"));
  await screen.findByTestId("owned-terminal");
  refused = true;
  fireEvent.click(screen.getByRole("button", { name: "Refresh assets" }));
  await waitFor(() => expect(screen.queryByTestId("owned-terminal")).not.toBeInTheDocument());
  expect(screen.queryAllByText("Owned asset")).toHaveLength(0);
  refused = false;
  fireEvent.click(screen.getByRole("button", { name: "Refresh assets" }));
  await screen.findByText("Owned asset");
  expect(screen.queryByTestId("owned-terminal")).not.toBeInTheDocument();
});
