export type JsonObject = Record<string, unknown>;

export interface TerminalToolCall {
  id?: string;
  name?: string;
  args?: JsonObject;
}

export interface TerminalToolArgs extends JsonObject {
  command?: string;
  reason?: string;
  question?: string;
  options?: string[];
}

export interface TerminalToolApproval {
  reason?: string;
  riskLevel?: string;
  isStateChanging?: boolean;
  targetAssets?: TerminalAsset[];
}

export interface TerminalMessagePart {
  type?: string;
  id?: string;
  text?: string;
  reasoning?: string;
  stepName?: string;
  state?: string;
  toolName?: string;
  toolCallId?: string;
  input?: JsonObject;
  output?: unknown;
  errorText?: string;
  _rawArgs?: string;
  approval?: TerminalToolApproval;
  [key: string]: unknown;
}

export interface TerminalMessage {
  id?: string;
  role?: 'user' | 'assistant' | 'system';
  type?: string;
  content?: string | TerminalMessagePart[];
  parts?: TerminalMessagePart[];
  tool_calls?: TerminalToolCall[];
  tool_call_id?: string;
  name?: string;
  additional_kwargs?: JsonObject;
}

export interface TerminalAsset {
  id: string;
  ip: string;
  name?: string;
  hostname?: string;
  port?: number | string;
  username?: string;
  group_id?: string | null;
  keychain_id?: string | null;
}

export interface TerminalCredential {
  id: string;
  name: string;
  type: string;
}

export interface TerminalAssetGroup {
  id: string;
  name: string;
}

export interface TerminalAssetInput {
  name: string;
  ip: string;
  port: number;
  username: string;
  keychain_id: string | null;
  group_id: string | null;
  password: string;
}

export interface TerminalToolInvocation {
  toolCallId?: string;
  toolName?: string;
  state?: string;
  input: TerminalToolArgs;
  args: TerminalToolArgs;
  approval?: TerminalToolApproval;
  output?: unknown;
  errorText?: string;
}

export function asJsonObject(value: unknown): JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

export function isTerminalMessagePart(value: unknown): value is TerminalMessagePart {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function asTerminalAssets(value: unknown): TerminalAsset[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item): TerminalAsset[] => {
    if (item === null || typeof item !== 'object' || Array.isArray(item)) return [];
    const record = item as Record<string, unknown>;
    const id = typeof record.id === 'string' ? record.id : '';
    const ip = typeof record.ip === 'string'
      ? record.ip
      : typeof record.hostname === 'string'
        ? record.hostname
        : '';
    if (!id || !ip) return [];
    return [{
      id,
      ip,
      name: typeof record.name === 'string' ? record.name : undefined,
      hostname: typeof record.hostname === 'string' ? record.hostname : undefined,
      port: typeof record.port === 'number' || typeof record.port === 'string' ? record.port : undefined,
      username: typeof record.username === 'string' ? record.username : undefined,
      group_id: typeof record.group_id === 'string' ? record.group_id : null,
      keychain_id: typeof record.keychain_id === 'string' ? record.keychain_id : null,
    }];
  });
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
