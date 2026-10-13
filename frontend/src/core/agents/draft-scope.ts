import { useCallback, useEffect, useRef } from "react";

import { useSkillImportContext } from "@/core/skills/import-context";

/** Dialogs remount for tenant/locale/name changes; async callbacks also check live tenancy. */
export function useDraftIsCurrent() {
  const context = useSkillImportContext();
  const key = context.key;
  const mounted = useRef(true);
  const latest = useRef(context);
  latest.current = context;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return useCallback(
    () => mounted.current && latest.current.key === key && latest.current.isCurrent(),
    [key],
  );
}
