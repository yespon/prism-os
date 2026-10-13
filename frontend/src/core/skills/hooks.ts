import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";


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
import { SkillMutationError } from "./mutations";
import { useSkillQueryIdentity } from "./query-identity";

import { loadSkills } from ".";

export function useSkills() {
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills", identity.key],
    enabled: identity.identityReady,
    retry: false,
    queryFn: async ({ signal }) => {
      if (!identity.isCurrent()) throw new Error("Skill read identity changed");
      const result = await loadSkills(signal);
      if (!identity.isCurrent() || signal.aborted)
        throw new Error("Skill read identity changed");
      return result;
    },
  });
  return {
    skills: identity.identityReady ? (data ?? []) : [],
    isLoading,
    error,
  };
}

export function useAvailableSkills({
  enabled = true,
}: { enabled?: boolean } = {}) {
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error } = useQuery({
    queryKey: ["availableSkills", identity.key],
    queryFn: async ({ signal }) => {
      if (!identity.isCurrent()) throw new Error("Skill read identity changed");
      const result = await loadAvailableSkills(signal);
      if (!identity.isCurrent() || signal.aborted)
        throw new Error("Skill read identity changed");
      return result;
    },
    enabled: enabled && identity.identityReady,
    retry: false,
    refetchOnWindowFocus: false,
  });

  return {
    skills: identity.identityReady ? (data ?? []) : [],
    isLoading,
    error,
  };
}

export function useTenantSkills({
  enabled = true,
}: { enabled?: boolean } = {}) {
  const identity = useSkillQueryIdentity();
  const { data, isLoading, error } = useQuery({
    queryKey: ["tenantSkills", identity.key],
    queryFn: async ({ signal }) => {
      if (!identity.isCurrent()) throw new Error("Skill read identity changed");
      const result = await loadTenantSkills(signal);
      if (!identity.isCurrent() || signal.aborted)
        throw new Error("Skill read identity changed");
      return result;
    },
    enabled: enabled && identity.identityReady,
    retry: false,
    refetchOnWindowFocus: false,
  });

  return {
    skills: identity.identityReady ? (data ?? []) : [],
    isLoading,
    error,
  };
}

export function useUpdateTenantSkill() {
  const queryClient = useQueryClient();
  const identity = useSkillQueryIdentity();
  const controls = useRef({
    key: identity.key,
    busy: new Set<string>(),
    blocked: new Set<string>(),
  });
  const [, redraw] = useState(0);
  if (controls.current.key !== identity.key)
    controls.current = {
      key: identity.key,
      busy: new Set(),
      blocked: new Set(),
    };
  const current = () =>
    controls.current.key === identity.key && identity.isCurrent();
  const mutation = useMutation({
    retry: false,
    mutationFn: async ({
      skillName,
      enabled,
      expectedResourceId,
    }: {
      skillName: string;
      enabled: boolean;
      expectedResourceId?: string;
    }) => {
      if (!current())
        throw new SkillMutationError(
          401,
          expectedResourceId,
          false,
          "Skill mutation identity changed",
        );
      const record = controls.current;
      const id = expectedResourceId ?? skillName;
      if (record.blocked.has(id) || record.busy.has(id))
        throw new SkillMutationError(
          409,
          expectedResourceId,
          false,
          "Inspect current enablement before another change",
        );
      record.busy.add(id);
      redraw((value) => value + 1);
      try {
        const result = await updateTenantSkill(skillName, enabled, {
          expectedResourceId,
          isCurrent: current,
        });
        if (!current())
          throw new SkillMutationError(
            401,
            expectedResourceId,
            false,
            "Skill mutation identity changed",
          );
        return result;
      } catch (error) {
        if (
          current() &&
          (!(error instanceof SkillMutationError) ||
            error.inspectionRequired ||
            error.status === 409)
        )
          record.blocked.add(id);
        throw error;
      } finally {
        record.busy.delete(id);
        if (current()) redraw((value) => value + 1);
      }
    },
    onSuccess: () => {
      if (!current()) return;
      void queryClient.invalidateQueries({
        queryKey: ["tenantSkills", identity.key],
      });
      void queryClient.invalidateQueries({
        queryKey: ["availableSkills", identity.key],
      });
    },
  });
  const inspectEnablement = async () => {
    if (!current()) throw new SkillMutationError(401);
    const queryKey = ["availableSkills", identity.key];
    const query = queryClient.getQueryCache().find({ queryKey, exact: true });
    if (!query?.isActive())
      throw new Error("Current resource list is unavailable");
    await queryClient.refetchQueries(
      { queryKey, exact: true, type: "active" },
      { throwOnError: true },
    );
    if (!current() || query.state.status !== "success")
      throw new Error("Current resource inspection did not complete");
    controls.current.blocked.clear();
    redraw((value) => value + 1);
  };
  return {
    ...mutation,
    enablementNeedsInspection: controls.current.blocked.size > 0,
    canToggleResource: (id?: string | null) =>
      !!id &&
      current() &&
      !controls.current.busy.has(id) &&
      !controls.current.blocked.has(id),
    inspectEnablement,
  };
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
  const identity = useSkillQueryIdentity();
  const live = useRef(identity.key); live.current = identity.key;
  const current = () => live.current === identity.key && identity.isCurrent();

  return useMutation({
    retry: false,
    mutationFn: (input: {
      name: string;
      description: string;
      instructions?: string | null;
      enabled?: boolean;
      category?: string;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) => {
      if (!current()) throw new SkillMutationError(401, undefined, false, "Skill creation identity changed");
      return createTenantSkill(input, {isCurrent: current});
    },
    onSuccess: () => {
      if (!current()) return;
      void queryClient.invalidateQueries({ queryKey: ["tenantSkills", identity.key] });
      void queryClient.invalidateQueries({ queryKey: ["availableSkills", identity.key] });
    },
  });
}

export function usePatchTenantSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: {
      skillName: string;
      expected_resource_id?: string;
      expected_file_sha256?: string;
      description?: string | null;
      instructions?: string | null;
      enabled?: boolean;
      category?: string;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) =>
      patchTenantSkill(input.skillName, {
        expected_resource_id: input.expected_resource_id,
        expected_file_sha256: input.expected_file_sha256,
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
  const identity = useSkillQueryIdentity();
  const live = useRef(identity.key); live.current = identity.key;
  const current = () => live.current === identity.key && identity.isCurrent();

  return useMutation({
    retry: false,
    mutationFn: (input: {
      name: string;
      description: string;
      instructions?: string | null;
      enabled?: boolean;
      changelog?: string | null;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) => {
      if (!current()) throw new SkillMutationError(401, undefined, false, "Skill creation identity changed");
      return createPersonalSkill(input, {isCurrent: current});
    },
    onSuccess: () => {
      if (!current()) return;
      void queryClient.invalidateQueries({ queryKey: ["availableSkills", identity.key] });
    },
  });
}

export function usePatchPersonalSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: {
      skillName: string;
      expected_resource_id?: string;
      expected_file_sha256?: string;
      description?: string | null;
      instructions?: string | null;
      enabled?: boolean;
      category?: string;
      bound_tools?: string[];
      prompt_template?: string | null;
      strategy?: string | null;
    }) =>
      patchPersonalSkill(input.skillName, {
        expected_resource_id: input.expected_resource_id,
        expected_file_sha256: input.expected_file_sha256,
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
