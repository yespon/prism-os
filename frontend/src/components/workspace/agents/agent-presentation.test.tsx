import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { zhCN } from "@/core/i18n/locales/zh-CN";
import { enUS } from "@/core/i18n/locales/en-US";
import type {
  Agent,
  CreateAgentRequest,
  UpdateAgentRequest,
} from "@/core/agents/types";
import type {
  AgentTemplatePreview,
  PersonalityResult,
} from "@/core/agents/catalog";
import { AgentTemplatePicker } from "./agent-template-picker";
import { AgentPresentationEditor } from "./agent-presentation-editor";
import { CreateAgentDialog } from "./create-agent-dialog";
import { EditAgentDialog } from "./edit-agent-dialog";
import { AgentWelcome } from "../agent-welcome";

const mock = vi.hoisted(() => ({
  tenant: "tenant-a",
  locale: "zh-CN",
  agent: null as Agent | null,
  load: vi.fn(),
  preview: vi.fn(),
  avatars: vi.fn(),
  questions: vi.fn(),
  score: vi.fn(),
  checkName: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  setInput: vi.fn(),
}));
vi.mock("@/core/agents/catalog", () => ({
  loadAgentCatalog: mock.load,
  previewAgentTemplate: mock.preview,
  loadAgentAvatars: mock.avatars,
  loadPersonalityQuestions: mock.questions,
  scorePersonality: mock.score,
}));
vi.mock("@/core/skills/import-context", () => ({ useSkillImportContext: () => ({ key: mock.tenant, identityReady: true, canShare: false, isCurrent: () => true }) }));
vi.mock("@/core/agents/hooks", () => ({ useTenantKey: () => mock.tenant }));
vi.mock("@/core/tenants/store", () => ({
  getCurrentTenantId: () => mock.tenant,
}));
vi.mock("@/core/agents/api", () => ({ checkAgentName: mock.checkName }));
vi.mock("@/core/agents", () => ({
  useSkills: () => ({ skills: [] }),
  useCreateAgent: () => ({ mutateAsync: mock.create, isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: mock.update, isPending: false }),
  useAgent: () => ({ agent: mock.agent, isLoading: false }),
  checkAgentName: mock.checkName,
}));
vi.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    locale: mock.locale,
    t: mock.locale === "en-US" ? enUS : zhCN,
  }),
}));
vi.mock("@/core/mcp/hooks", () => ({
  useAvailableMcpConfig: () => ({ rawArray: [], isLoading: false }),
}));
vi.mock("@/core/models/hooks", () => ({
  useAvailableModels: () => ({ models: [], isLoading: false }),
}));
vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: () => ({ data: { role: "tenant_member" } }),
}));
vi.mock("./agent-avatar", () => ({
  AgentAvatar: ({ avatarId }: { avatarId: string }) => (
    <span data-testid="avatar">{avatarId}</span>
  ),
}));
vi.mock("@/components/ai-elements/prompt-input", () => ({
  usePromptInputController: () => ({ textInput: { setInput: mock.setInput } }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const expert: AgentTemplatePreview = {
  id: "expert:general-assistant",
  kind: "expert",
  name: "General expert",
  suggested_name: "general-assistant",
  description: "Expert description",
  locale: "zh",
  division: "experts",
  bundled_resources: ["skills/example"],
  excluded_resources: ["skills/pptx"],
  revision: "b6",
  system_prompt: "Expert instructions",
  welcome_message: "Expert welcome",
  avatar_id: "experts:general-assistant",
  quick_prompts: [
    {
      title: "First question",
      prompt: "Please inspect this draft",
      description: "",
    },
  ],
};
const result: PersonalityResult = {
  code: "INTJ",
  dimensions: { EI: ["I", 85], SN: ["N", 85], TF: ["T", 85], JP: ["J", 85] },
  automatic_apply: false,
};
const questions = Array.from({ length: 28 }, (_, index) => ({
  id: index + 1,
  question: `Question ${index + 1}`,
  option_a: "A answer",
  option_b: "B answer",
}));

beforeEach(() => {
  vi.resetAllMocks();
  mock.tenant = "tenant-a";
  mock.locale = "zh-CN";
  mock.agent = null;
  mock.load.mockResolvedValue({
    templates: [
      expert,
      { ...expert, id: "expert:second", name: "Second expert" },
      {
        ...expert,
        id: "subagent:specialist",
        kind: "subagent",
        name: "Specialist",
      },
    ],
    personas: [
      { code: "INTJ", name_zh: "建筑师", name_en: "Architect" },
      { code: "ENFP", name_zh: "竞选者", name_en: "Campaigner" },
    ],
  });
  mock.preview.mockResolvedValue(expert);
  mock.avatars.mockResolvedValue({
    avatars: [{ id: "personas:INTJ", label: "INTJ" }],
  });
  mock.questions.mockResolvedValue({ questions });
  mock.score.mockResolvedValue(result);
  mock.checkName.mockResolvedValue({ available: true });
  mock.create.mockResolvedValue({});
  mock.update.mockResolvedValue({});
});
afterEach(cleanup);

function picker(overrides = {}) {
  return {
    open: true,
    locale: "zh" as const,
    templateId: "",
    personaCode: "",
    onTemplate: vi.fn(),
    onPersona: vi.fn(),
    ...overrides,
  };
}
async function selectExpert() {
  await waitFor(() =>
    expect(screen.getByLabelText("专家模板")).not.toBeDisabled(),
  );
  fireEvent.change(screen.getByLabelText("专家模板"), {
    target: { value: expert.id },
  });
}

describe("Template request isolation and resources", () => {
  it.each(["close", "locale", "tenant"])(
    "discards an old preview after %s",
    async (kind) => {
      const pending = deferred<AgentTemplatePreview>();
      mock.preview.mockReturnValue(pending.promise);
      const props = picker();
      const view = render(<AgentTemplatePicker {...props} />);
      await selectExpert();
      const signal = mock.preview.mock.calls[0]?.[2] as AbortSignal;
      if (kind === "tenant") mock.tenant = "tenant-b";
      view.rerender(
        <AgentTemplatePicker
          {...props}
          open={kind !== "close"}
          locale={kind === "locale" ? "en" : "zh"}
        />,
      );
      await act(async () => pending.resolve(expert));
      expect(signal.aborted).toBe(true);
      expect(props.onTemplate).not.toHaveBeenCalled();
    },
  );
  it("only applies the newest preview and cancels selection on manual mode", async () => {
    const first = deferred<AgentTemplatePreview>();
    const second = deferred<AgentTemplatePreview>();
    mock.preview
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const props = picker();
    render(<AgentTemplatePicker {...props} />);
    await selectExpert();
    fireEvent.change(screen.getByLabelText("专家模板"), {
      target: { value: "expert:second" },
    });
    await act(async () => second.resolve({ ...expert, id: "expert:second" }));
    await act(async () => first.resolve(expert));
    expect(props.onTemplate).toHaveBeenCalledTimes(1);
    expect(props.onTemplate.mock.calls[0]?.[0].id).toBe("expert:second");
    const third = deferred<AgentTemplatePreview>();
    mock.preview.mockReturnValueOnce(third.promise);
    await selectExpert();
    fireEvent.change(screen.getByLabelText("专家模板"), {
      target: { value: "manual" },
    });
    await act(async () => third.resolve(expert));
    expect(props.onTemplate).toHaveBeenLastCalledWith(null);
    expect(props.onTemplate).toHaveBeenCalledTimes(2);
  });
  it("clears old catalog contents on tenant change and retries failures", async () => {
    const props = picker({ templateId: expert.id });
    const view = render(<AgentTemplatePicker {...props} />);
    await screen.findByText(/原目录配套文件 1 项/);
    expect(screen.getByText(/待独立实现：/)).toHaveTextContent("skills/pptx");
    mock.tenant = "tenant-b";
    mock.load.mockRejectedValueOnce(new Error("offline"));
    view.rerender(<AgentTemplatePicker {...props} />);
    await screen.findByRole("alert");
    expect(
      screen.queryByText("General expert", { selector: "option" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText("General expert", { selector: "option" });
    fireEvent.change(screen.getByLabelText("模板类型"), {
      target: { value: "subagent" },
    });
    expect(
      screen.queryByText("Second expert", { selector: "option" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Specialist", { selector: "option" }),
    ).toBeInTheDocument();
  });
  it("ignores an old catalog response after locale change", async () => {
    const old = deferred<Awaited<ReturnType<typeof mock.load>>>();
    mock.load.mockReturnValueOnce(old.promise);
    const props = picker();
    const view = render(<AgentTemplatePicker {...props} />);
    view.rerender(<AgentTemplatePicker {...props} locale="en" />);
    await screen.findByText("General expert", { selector: "option" });
    await act(async () =>
      old.resolve({
        templates: [{ ...expert, name: "Old language" }],
        personas: [],
      }),
    );
    expect(screen.queryByText("Old language")).not.toBeInTheDocument();
  });
});

function fields(overrides = {}) {
  return {
    open: true,
    locale: "zh" as const,
    welcomeMessage: "",
    avatarId: "",
    quickPrompts: [],
    onQuickPrompts: vi.fn(),
    onWelcome: vi.fn(),
    onAvatar: vi.fn(),
    onPersona: vi.fn(),
    ...overrides,
  };
}
async function fillQuestionnaire() {
  const button = await screen.findByRole("button", {
    name: "通过测验选择人格",
  });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  for (let index = 1; index <= 28; index++)
    fireEvent.click(screen.getByLabelText(`${index} A`));
  fireEvent.click(screen.getByRole("button", { name: "查看结果 (28/28)" }));
}

describe("Questionnaire draft flow", () => {
  // The complete 28-choice dialog flow needs a bounded budget on shared runners.
  it("requires all 28 choices and only applies the confirmed result", async () => {
    const props = fields();
    render(<AgentPresentationEditor {...props} />);
    await fillQuestionnaire();
    await screen.findByText(/INTJ · EI:/);
    expect(mock.score).toHaveBeenCalledWith(
      Object.fromEntries(
        questions.map((question) => [String(question.id), "A"]),
      ),
      expect.any(AbortSignal),
    );
    expect(props.onPersona).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "将此人格应用到草稿" }));
    expect(props.onPersona).toHaveBeenCalledWith("INTJ");
    expect(mock.create).not.toHaveBeenCalled();
    expect(mock.update).not.toHaveBeenCalled();
  }, 15_000);
  it.each(["close", "locale", "tenant"])(
    "clears the questionnaire and discards the pending score after %s",
    async (kind) => {
      const pending = deferred<PersonalityResult>();
      mock.score.mockReturnValueOnce(pending.promise);
      const props = fields();
      const view = render(<AgentPresentationEditor {...props} />);
      await fillQuestionnaire();
      const signal = mock.score.mock.calls[0]?.[1] as AbortSignal;
      if (kind === "tenant") mock.tenant = "tenant-b";
      view.rerender(
        <AgentPresentationEditor
          {...props}
          open={kind !== "close"}
          locale={kind === "locale" ? "en" : "zh"}
        />,
      );
      await act(async () => pending.resolve(result));
      expect(signal.aborted).toBe(true);
      expect(screen.queryByText(/INTJ · EI:/)).not.toBeInTheDocument();
      expect(props.onPersona).not.toHaveBeenCalled();
    },
  );
});

function savedAgent(request: CreateAgentRequest): Agent {
  return {
    id: "agent-id",
    name: request.name,
    description: request.description ?? "",
    model: null,
    tool_groups: [],
    skills: [],
    enabled: true,
    tags: [],
    base_system_prompt: request.system_prompt,
    system_prompt: `${request.system_prompt}\n\nRendered persona`,
    presentation: {
      template_id: request.template_id ?? null,
      template_locale: request.template_locale ?? "zh",
      persona_mbti: request.persona_mbti ?? null,
      welcome_message: request.welcome_message ?? "",
      avatar_id: request.avatar_id ?? null,
      quick_prompts: request.quick_prompts ?? [],
      bundled_resources_installed: false,
      excluded_resources: expert.excluded_resources,
    },
  };
}

describe("Create, edit and reopen", () => {
  // The complete 28-choice dialog flow needs a bounded budget on shared runners.
  it("saves edited template, persona, avatar, welcome and starters, then reopens without duplicating persona", async () => {
    mock.create.mockImplementation(async (request: CreateAgentRequest) => {
      mock.agent = savedAgent(request);
      return mock.agent;
    });
    const create = render(<CreateAgentDialog open onOpenChange={vi.fn()} />);
    await selectExpert();
    await screen.findByDisplayValue("Expert instructions");
    fireEvent.change(screen.getByDisplayValue("Expert instructions"), {
      target: { value: "Edited base instructions" },
    });
    fireEvent.change(screen.getByLabelText("欢迎语"), {
      target: { value: "Edited welcome" },
    });
    fireEvent.change(screen.getByLabelText("头像"), {
      target: { value: "personas:INTJ" },
    });
    fireEvent.change(screen.getByLabelText("快捷提问内容 1"), {
      target: { value: "Edited starter" },
    });
    await fillQuestionnaire();
    await screen.findByText(/INTJ · EI:/);
    fireEvent.click(screen.getByRole("button", { name: "将此人格应用到草稿" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "保存配置" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    await waitFor(() => expect(mock.create).toHaveBeenCalled());
    expect(mock.create.mock.calls[0]?.[0]).toMatchObject({
      template_id: expert.id,
      system_prompt: "Edited base instructions",
      persona_mbti: "INTJ",
      avatar_id: "personas:INTJ",
      welcome_message: "Edited welcome",
      quick_prompts: [{ prompt: "Edited starter" }],
    });
    create.unmount();
    const edit = render(
      <EditAgentDialog
        open
        agentName="general-assistant"
        onOpenChange={vi.fn()}
      />,
    );
    expect(
      screen.getByDisplayValue("Edited base instructions"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("欢迎语")).toHaveValue("Edited welcome");
    expect(screen.getByLabelText("快捷提问内容 1")).toHaveValue(
      "Edited starter",
    );
    fireEvent.change(screen.getByLabelText("欢迎语"), {
      target: { value: "Reopened welcome" },
    });
    fireEvent.change(screen.getByLabelText("人格风格"), {
      target: { value: "none" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    await waitFor(() => expect(mock.update).toHaveBeenCalled());
    const changed = mock.update.mock.calls[0]?.[0]
      .request as UpdateAgentRequest;
    expect(changed).toMatchObject({
      system_prompt: "Edited base instructions",
      persona_mbti: null,
      welcome_message: "Reopened welcome",
    });
    expect(changed).not.toHaveProperty("is_shared");
    mock.agent = {
      ...mock.agent!,
      presentation: {
        ...mock.agent!.presentation!,
        welcome_message: changed.welcome_message!,
        persona_mbti: null,
      },
    };
    edit.unmount();
    render(
      <EditAgentDialog
        open
        agentName="general-assistant"
        onOpenChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("欢迎语")).toHaveValue("Reopened welcome");
  }, 15_000);
  it.each(["locale", "tenant"])(
    "clears the existing create draft on %s change",
    async (kind) => {
      const view = render(<CreateAgentDialog open onOpenChange={vi.fn()} />);
      fireEvent.change(screen.getByLabelText("欢迎语"), {
        target: { value: "old draft" },
      });
      if (kind === "tenant") mock.tenant = "tenant-b";
      else mock.locale = "en-US";
      view.rerender(<CreateAgentDialog open onOpenChange={vi.fn()} />);
      expect(
        screen.getByLabelText(kind === "locale" ? "Welcome message" : "欢迎语"),
      ).toHaveValue("");
    },
  );
  it("does not apply a stale name check to a newer name", async () => {
    const first = deferred<{ available: boolean }>();
    mock.checkName.mockReturnValueOnce(first.promise);
    render(<CreateAgentDialog open onOpenChange={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("智能体名称"), {
      target: { value: "first-name" },
    });
    await waitFor(() =>
      expect(mock.checkName).toHaveBeenCalledWith("first-name", false),
    );
    fireEvent.change(screen.getByPlaceholderText("智能体名称"), {
      target: { value: "second-name" },
    });
    await waitFor(() =>
      expect(mock.checkName).toHaveBeenCalledWith("second-name", false),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "保存配置" })).toBeEnabled(),
    );
    await act(async () => first.resolve({ available: false }));
    expect(screen.getByRole("button", { name: "保存配置" })).toBeEnabled();
  });
  it("ignores a completed save callback after tenancy changes", async () => {
    const pending = deferred<Agent>();
    mock.create.mockReturnValueOnce(pending.promise);
    const close = vi.fn();
    const success = vi.fn();
    const view = render(
      <CreateAgentDialog open onOpenChange={close} onSuccess={success} />,
    );
    fireEvent.change(screen.getByPlaceholderText("智能体名称"), {
      target: { value: "saving-agent" },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "保存配置" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    mock.tenant = "tenant-b";
    view.rerender(
      <CreateAgentDialog open onOpenChange={close} onSuccess={success} />,
    );
    await act(async () =>
      pending.resolve(savedAgent({ name: "saving-agent" })),
    );
    expect(close).not.toHaveBeenCalled();
    expect(success).not.toHaveBeenCalled();
  });
  it("fills a starter into chat draft without submitting it", () => {
    const agent = savedAgent({
      name: "welcome",
      welcome_message: "Welcome",
      quick_prompts: expert.quick_prompts,
    });
    render(<AgentWelcome agent={agent} agentName="welcome" />);
    fireEvent.click(screen.getByRole("button", { name: "First question" }));
    expect(mock.setInput).toHaveBeenCalledWith("Please inspect this draft");
    expect(mock.create).not.toHaveBeenCalled();
    expect(mock.update).not.toHaveBeenCalled();
  });
});
