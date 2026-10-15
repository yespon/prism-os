export interface SkillResourceReference {
  name: string;
  scope: "global" | "tenant" | "personal";
  resource_id: string;
}

export interface AgentQuickPrompt {
  title: string;
  prompt: string;
  description: string;
}

export interface AgentPresentation {
  quick_prompts: AgentQuickPrompt[];
  welcome_message: string;
  avatar_id: string | null;
  template_locale: "zh" | "en";
  persona_mbti: string | null;
  template_id: string | null;
  bundled_resources_installed: boolean;
  excluded_resources: string[];
}

export interface Agent {
  revision?: string | null;
  skill_binding_mode?: "all" | "selected" | "unresolved" | null;
  skill_resources?: SkillResourceReference[] | null;
  presentation?: AgentPresentation;
  base_system_prompt?: string;
  id: string;
  name: string;
  description: string;
  model: string | null;
  tool_groups: string[] | null;
  system_prompt?: string | null;
  /** @deprecated Use system_prompt */
  soul?: string | null;
  skills: string[];
  enabled: boolean;
  tags: string[];
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  is_shared?: boolean;
}

export interface Skill {
  scope?: "global" | "tenant" | "personal";
  resource_id?: string | null;
  name: string;
  description: string;
  category: string;
  enabled: boolean;
}

export interface CreateAgentRequest {
  skill_binding_mode?: "all" | "selected";
  skill_resources?: SkillResourceReference[];
  quick_prompts?: AgentQuickPrompt[];
  welcome_message?: string;
  avatar_id?: string | null;
  template_id?: string;
  template_locale?: "zh" | "en";
  persona_mbti?: string;
  name: string;
  description?: string;
  model?: string | null;
  tool_groups?: string[] | null;
  system_prompt?: string;
  /** @deprecated Use system_prompt */
  soul?: string;
  skills?: string[];
  tags?: string[];
  enabled?: boolean;
  is_shared?: boolean;
}

export interface UpdateAgentRequest {
  expected_agent_id?: string;
  expected_revision?: string;
  skill_binding_mode?: "all" | "selected";
  skill_resources?: SkillResourceReference[];
  template_locale?: "zh" | "en";
  persona_mbti?: string | null;
  quick_prompts?: AgentQuickPrompt[];
  welcome_message?: string;
  avatar_id?: string | null;
  description?: string | null;
  model?: string | null;
  tool_groups?: string[] | null;
  system_prompt?: string | null;
  /** @deprecated Use system_prompt */
  soul?: string | null;
  skills?: string[] | null;
  enabled?: boolean | null;
  tags?: string[] | null;
  is_shared?: boolean | null;
}

export interface CopyAgentRequest {
  name: string;
  source_agent_id: string;
  source_revision: string;
  is_shared: boolean;
  skill_binding_mode: "all" | "selected";
  skill_resources: SkillResourceReference[];
}
