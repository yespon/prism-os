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
  name: string;
  description: string;
  category: string;
  enabled: boolean;
}

export interface CreateAgentRequest {
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
