"use client";

import { readMigratedStorage, removePrismOSStorage, writePrismOSStorage } from "@/core/storage/brand-migration";

const TENANT_STORAGE_KEY = "prismos_current_tenant_id";
const LEGACY_TENANT_STORAGE_KEY = "opsintech.current_tenant_id";

let cachedTenantId: string | null = null;
const listeners = new Set<(tenantId: string | null) => void>();

function isBrowser() {
  return typeof window !== "undefined";
}

function normalizeTenantId(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function notify(tenantId: string | null) {
  for (const listener of listeners) {
    listener(tenantId);
  }
}

export function getCurrentTenantId(): string | null {
  if (cachedTenantId !== null) {
    return cachedTenantId;
  }
  if (!isBrowser()) {
    return null;
  }
  cachedTenantId = readMigratedStorage({
    storage: window.localStorage,
    key: TENANT_STORAGE_KEY,
    legacyKey: LEGACY_TENANT_STORAGE_KEY,
    parse: (raw) => {
      const tenantId = normalizeTenantId(raw);
      if (!tenantId) throw new Error("Invalid tenant id");
      return tenantId;
    },
  });
  return cachedTenantId;
}

export function setCurrentTenantId(tenantId: string | null) {
  const normalized = normalizeTenantId(tenantId);
  cachedTenantId = normalized;

  if (isBrowser()) {
    if (normalized) {
      writePrismOSStorage(window.localStorage, TENANT_STORAGE_KEY, normalized);
    } else {
      removePrismOSStorage(window.localStorage, TENANT_STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent("prismos:tenant-changed", { detail: { tenantId: normalized } }));
  }

  notify(normalized);
}

export function subscribeTenantChange(listener: (tenantId: string | null) => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}


export function clearTenantId(): void {
  setCurrentTenantId(null);
}
