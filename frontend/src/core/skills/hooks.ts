import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createTenantSkill,
  deleteTenantSkill,
  importTenantSkill,
  loadAvailableSkills,
  loadTenantSkills,
  patchTenantSkill,
  updateTenantSkill,
  createPersonalSkill,
  patchPersonalSkill,
  deletePersonalSkill,
  importPersonalSkill,
} from "./api";
import { useSkillQueryIdentity } from "./query-identity";

import { loadSkills } from ".";

export function useSkills() {
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills", identity.key],
    enabled: identity.identityReady,
    retry: false,
    queryFn: async ({signal}) => {
      if (!identity.isCurrent()) throw new Error("Skill read identity changed");
      const result = await loadSkills(signal);
      if (!identity.isCurrent() || signal.aborted) throw new Error("Skill read identity changed");
      return result;
    },
  });
  return { skills: identity.identityReady ? data ?? [] : [], isLoading, error };
}

export function useAvailableSkills({ enabled = true }: { enabled?: boolean } = {}) {
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error } = useQuery({
    queryKey: ["availableSkills", identity.key],
    queryFn: async ({signal}) => {
      if (!identity.isCurrent()) throw new Error("Skill read identity changed");
      const result = await loadAvailableSkills(signal);
      if (!identity.isCurrent() || signal.aborted) throw new Error("Skill read identity changed");
      return result;
    },
    enabled: enabled && identity.identityReady,
    retry: false,
    refetchOnWindowFocus: false,
  });

  return {
    skills: identity.identityReady ? data ?? [] : [],
    isLoading,
    error,
  };
}

export function useTenantSkills({ enabled = true }: { enabled?: boolean } = {}) {
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error } = useQuery({
    queryKey: ["tenantSkills", identity.key],
    queryFn: async ({signal}) => {
      if (!identity.isCurrent()) throw new Error("Skill read identity changed");
      const result = await loadTenantSkills(signal);
      if (!identity.isCurrent() || signal.aborted) throw new Error("Skill read identity changed");
      return result;
    },
    enabled: enabled && identity.identityReady,
    retry: false,
    refetchOnWindowFocus: false,
  });

  return {
    skills: identity.identityReady ? data ?? [] : [],
    isLoading,
    error,
  };
}

export function useUpdateTenantSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ skillName, enabled }: { skillName: string; enabled: boolean }) =>
      updateTenantSkill(skillName, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenantSkills"] });
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function useDeleteTenantSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillName: string) => deleteTenantSkill(skillName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenantSkills"] });
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function useCreateTenantSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: {
      name: string;
      description: string;
      instructions?: string | null;
      enabled?: boolean;
      category?: string;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) =>
      createTenantSkill(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenantSkills"] });
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function usePatchTenantSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: {
      skillName: string;
      description?: string | null;
      instructions?: string | null;
      enabled?: boolean;
      category?: string;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) =>
      patchTenantSkill(input.skillName, {
        description: input.description,
        instructions: input.instructions,
        enabled: input.enabled,
        category: input.category,
        bound_tools: input.bound_tools,
        prompt_template: input.prompt_template,
        strategy: input.strategy,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenantSkills"] });
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function useCreatePersonalSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: {
      name: string;
      description: string;
      instructions?: string | null;
      enabled?: boolean;
      changelog?: string | null;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) =>
      createPersonalSkill(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function usePatchPersonalSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: {
      skillName: string;
      description?: string | null;
      instructions?: string | null;
      enabled?: boolean;
      category?: string;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) =>
      patchPersonalSkill(input.skillName, {
        description: input.description,
        instructions: input.instructions,
        enabled: input.enabled,
        category: input.category,
        bound_tools: input.bound_tools,
        prompt_template: input.prompt_template,
        strategy: input.strategy,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function useDeletePersonalSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillName: string) => deletePersonalSkill(skillName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function useImportTenantSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => importTenantSkill(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tenantSkills"] });
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}

export function useImportPersonalSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => importPersonalSkill(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["availableSkills"] });
    },
  });
}
