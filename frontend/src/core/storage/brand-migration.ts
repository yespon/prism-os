export interface MigratedStorageOptions<T> {
  storage: Storage;
  key: string;
  legacyKey: string;
  parse: (raw: string) => T;
}

/**
 * Read the canonical browser key, migrating one valid legacy value when needed.
 *
 * A legacy value is removed only after the copied raw value can be read back
 * and parsed successfully. The migration warning intentionally contains no
 * storage contents or legacy key names.
 */
export function readMigratedStorage<T>({
  storage,
  key,
  legacyKey,
  parse,
}: MigratedStorageOptions<T>): T | null {
  const current = storage.getItem(key);
  if (current !== null) {
    try {
      return parse(current);
    } catch {
      return null;
    }
  }

  const legacy = storage.getItem(legacyKey);
  if (legacy === null) {
    return null;
  }

  try {
    parse(legacy);
    storage.setItem(key, legacy);
    const written = storage.getItem(key);
    if (written !== legacy) {
      return null;
    }
    const verified = parse(written);
    storage.removeItem(legacyKey);
    return verified;
  } catch {
    console.warn("[PrismOS migration] Unable to migrate legacy browser storage");
    return null;
  }
}

export function writePrismOSStorage(storage: Storage, key: string, value: string): void {
  storage.setItem(key, value);
}

export function removePrismOSStorage(storage: Storage, key: string): void {
  storage.removeItem(key);
}
