import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { useAvailableSkills } from "@/core/skills/hooks";
import { useSkillQueryIdentity } from "@/core/skills/query-identity";
import { getCurrentTenantId, subscribeTenantChange } from "@/core/tenants/store";

import {
  createAgent,
  deleteAgent,
  getAgent,
  listAgents,
  updateAgent,
} from "./api";
import type { CreateAgentRequest, UpdateAgentRequest } from "./types";

export function useTenantKey() {
  return useSyncExternalStore(subscribeTenantChange, () => getCurrentTenantId() ?? "_", () => "_");
}

export function useAgents() {
  const tenantKey = useTenantKey();
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["agents", tenantKey, identity.key],
    queryFn: async () => { if (!identity.isCurrent()) throw new Error("Agent identity changed"); const data = await listAgents(); if (!identity.isCurrent()) throw new Error("Agent identity changed"); return data; },
    enabled: identity.identityReady,
  });
  return { agents: data ?? [], isLoading, error, refetch };
}

export function useAgent(name: string | null | undefined) {
  const tenantKey = useTenantKey();
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error } = useQuery({
    queryKey: ["agents", tenantKey, identity.key, name],
    queryFn: async () => { if (!identity.isCurrent()) throw new Error("Agent identity changed"); const data = await getAgent(name!); if (!identity.isCurrent()) throw new Error("Agent identity changed"); return data; },
    enabled: !!name && identity.identityReady,
  });
  return { agent: data ?? null, isLoading, error };
}

export function useSkills() {
  const result = useAvailableSkills();
  return { ...result, skills: result.skills.map((skill) => ({...skill, scope: skill.scope as "global" | "tenant" | "personal", category: skill.scope === "global" ? "public" : "custom"})) };
}

export function useCreateAgent() {
  const queryClient = useQueryClient();
  const tenantKey = useTenantKey();
  const identity = useSkillQueryIdentity();
  return useMutation({
    mutationFn: (request: CreateAgentRequest) => createAgent(request, {isCurrent:identity.isCurrent}),
    onSuccess: () => {
      if (!identity.isCurrent()) return;
      void queryClient.invalidateQueries({ queryKey: ["agents", tenantKey, identity.key] });
    },
  });
}

export function useUpdateAgent() {
  const queryClient = useQueryClient();
  const tenantKey = useTenantKey();
  const identity = useSkillQueryIdentity();
  return useMutation({
    mutationFn: ({
      name,
      request,
    }: {
      name: string;
      request: UpdateAgentRequest;
    }) => updateAgent(name, request, {isCurrent:identity.isCurrent}),
    onSuccess: (_data, { name }) => {
      if (!identity.isCurrent()) return;
      void queryClient.invalidateQueries({ queryKey: ["agents", tenantKey, identity.key] });
      void queryClient.invalidateQueries({ queryKey: ["agents", tenantKey, identity.key, name] });
    },
  });
}

export function useToggleAgent() {
  const queryClient = useQueryClient();
  const tenantKey = useTenantKey();
  const identity = useSkillQueryIdentity();
  return useMutation({
    mutationFn: ({
      name,
      enabled,
    }: {
      name: string;
      enabled: boolean;
    }) => updateAgent(name, { enabled }, {isCurrent:identity.isCurrent}),
    onSuccess: (_data, { name }) => {
      if (!identity.isCurrent()) return;
      void queryClient.invalidateQueries({ queryKey: ["agents", tenantKey, identity.key] });
      void queryClient.invalidateQueries({ queryKey: ["agents", tenantKey, identity.key, name] });
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  const tenantKey = useTenantKey();
  const identity = useSkillQueryIdentity();
  return useMutation({
    mutationFn: (name: string) => deleteAgent(name),
    onSuccess: () => {
      if (!identity.isCurrent()) return;
      void queryClient.invalidateQueries({ queryKey: ["agents", tenantKey, identity.key] });
    },
  });
}
