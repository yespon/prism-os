import { useCallback, useEffect, useRef } from "react";
import { getCurrentTenantId } from "@/core/tenants/store";
import { useTenantKey } from "./hooks";

/** Dialogs remount for tenant/locale/name changes; async callbacks also check live tenancy. */
export function useDraftIsCurrent() {
  const tenant = useTenantKey();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return useCallback(
    () => mounted.current && tenant === (getCurrentTenantId() ?? "_"),
    [tenant],
  );
}
