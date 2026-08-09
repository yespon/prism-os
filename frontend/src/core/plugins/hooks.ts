"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchPlugins, type PluginInfo } from "./api";

export function usePlugins() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["plugins"],
    queryFn: fetchPlugins,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const plugins: PluginInfo[] = data?.plugins ?? [];

  const hiddenNavIds = new Set<string>();
  for (const p of plugins) {
    if (!p.enabled) {
      for (const navId of p.frontendNavIds) {
        hiddenNavIds.add(navId);
      }
    }
  }

  return { plugins, hiddenNavIds, isLoading, error };
}