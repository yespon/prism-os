import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { Agent } from "@/core/agents";
import type { AgentMutationError, AgentReadError } from "@/core/agents/api";

import { CopyAgentDialog } from "./copy-agent-dialog";

const state = vi.hoisted(() => ({ current:true,copy:vi.fn(),get:vi.fn(),success:vi.fn(),close:vi.fn() }));
vi.mock("@/core/agents", async () => {
  const actual = await vi.importActual<{AgentMutationError:typeof AgentMutationError;AgentReadError:typeof AgentReadError}>("@/core/agents/api");
  return {...actual,copyAgent:state.copy,getAgent:state.get,useSkills:()=>({skills:[{name:"collision",scope:"personal",resource_id:"personal-current",category:"custom",enabled:true,description:"Personal"}]})};
});
vi.mock("@/core/agents/draft-scope",()=>({useDraftIsCurrent:()=>()=>state.current}));
vi.mock("@/core/skills/import-context",()=>({useSkillImportContext:()=>({key:"tenant-a:actor-a"})}));
vi.mock("@/core/tenants/hooks",()=>({useCurrentTenant:()=>({data:{role:"tenant_admin"}})}));
vi.mock("sonner",()=>({toast:{success:vi.fn(),error:vi.fn(),info:vi.fn()}}));
const original: Agent = {id:"source-id",revision:"a".repeat(64),name:"source",description:"Source",model:null,tool_groups:[],skills:["collision"],enabled:true,tags:[],skill_binding_mode:"selected",skill_resources:[{name:"collision",scope:"personal",resource_id:"personal-current"}]};
beforeEach(()=>{state.current=true;vi.clearAllMocks();state.copy.mockResolvedValue({id:"copy-id"});});
afterEach(cleanup);
const show = () => render(<CopyAgentDialog agent={original} onClose={state.close} onSuccess={state.success} />);

it("submits source identity/version and the explicitly visible target resource choice",async()=>{
  show();
  fireEvent.click(screen.getByRole("button",{name:"确认创建副本"}));
  await waitFor(()=>expect(state.copy).toHaveBeenCalledTimes(1));
  expect(state.copy).toHaveBeenCalledWith("source",{
    name:"source-copy",source_agent_id:"source-id",source_revision:"a".repeat(64),is_shared:false,
    skill_binding_mode:"selected",skill_resources:original.skill_resources,
  },expect.objectContaining({isCurrent:expect.any(Function)}));
  await waitFor(()=>expect(state.close).toHaveBeenCalledTimes(1));
});

it("blocks sharing inherited personal choices until the user explicitly clears them",()=>{
  show();
  fireEvent.click(screen.getByRole("switch"));
  expect(screen.getByRole("button",{name:"确认创建副本"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"清空并重新选择技能"}));
  expect(screen.getByRole("button",{name:"确认创建副本"})).not.toBeDisabled();
  expect(state.copy).not.toHaveBeenCalled();
});

it("checks an existing target after an unknown save instead of submitting again",async()=>{
  const {AgentMutationError}=await import("@/core/agents/api");
  state.copy.mockRejectedValue(new AgentMutationError(503,true));
  state.get.mockResolvedValue({...original,id:"existing-copy",name:"source-copy"});
  show();
  fireEvent.click(screen.getByRole("button",{name:"确认创建副本"}));
  await screen.findByText(/复制结果或来源已变化/);
  expect(screen.getByRole("button",{name:"确认创建副本"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"重新读取来源"}));
  await waitFor(()=>expect(state.get).toHaveBeenCalledWith("source-copy"));
  await waitFor(()=>expect(state.close).toHaveBeenCalledTimes(1));
  expect(state.copy).toHaveBeenCalledTimes(1);
});

it("discards a late successful response after the current draft identity changes",async()=>{
  state.copy.mockImplementation(async()=>{state.current=false;return {id:"copy-id"};});
  show();
  fireEvent.click(screen.getByRole("button",{name:"确认创建副本"}));
  await waitFor(()=>expect(state.copy).toHaveBeenCalledTimes(1));
  expect(state.success).not.toHaveBeenCalled();
  expect(state.close).not.toHaveBeenCalled();
});


it("does not read the source under a new identity after a late target 404", async () => {
  const { AgentMutationError, AgentReadError } = await import("@/core/agents/api");
  state.copy.mockRejectedValue(new AgentMutationError(503, true));
  state.get.mockImplementation(async () => {
    state.current = false;
    throw new AgentReadError(404);
  });
  show();
  fireEvent.click(screen.getByRole("button", { name: "确认创建副本" }));
  await screen.findByText(/复制结果或来源已变化/);
  fireEvent.click(screen.getByRole("button", { name: "重新读取来源" }));
  await waitFor(() => expect(state.get).toHaveBeenCalledTimes(1));
  expect(state.get).toHaveBeenCalledWith("source-copy");
  expect(state.success).not.toHaveBeenCalled();
  expect(state.close).not.toHaveBeenCalled();
});


it("inspects the dispatched target even if the editable name changes after an unknown result", async () => {
  const { AgentMutationError } = await import("@/core/agents/api");
  state.copy.mockRejectedValue(new AgentMutationError(503, true));
  state.get.mockResolvedValue({ ...original, id: "created-copy", name: "source-copy" });
  show();
  fireEvent.click(screen.getByRole("button", { name: "确认创建副本" }));
  await screen.findByText(/复制结果或来源已变化/);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "different-copy" } });
  fireEvent.click(screen.getByRole("button", { name: "重新读取来源" }));
  await waitFor(() => expect(state.get).toHaveBeenCalledWith("source-copy"));
  expect(state.copy).toHaveBeenCalledTimes(1);
});
