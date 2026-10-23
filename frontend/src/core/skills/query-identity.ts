"use client";

import { useSession } from "@/core/auth/hooks";
import { useSkillImportContext } from "@/core/skills/import-context";

export function useSkillQueryIdentity() {
  const context = useSkillImportContext();
  const { data: session } = useSession();
  return { ...context, key: JSON.stringify([context.key, session?.user.role]) };
}
