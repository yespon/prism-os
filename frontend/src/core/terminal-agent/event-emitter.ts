/**
 * Lightweight typed EventEmitter for browser environments.
 * Replaces Node.js EventEmitter used in Chaterm's InteractionDetector.
 */

type EventHandler = (...args: never[]) => void;

export class TypedEventEmitter<Events extends Record<string, unknown[]>> {
  private _listeners = new Map<string, Set<EventHandler>>();

  on<K extends string & keyof Events>(event: K, listener: (...args: Events[K]) => void): this {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set());
    }
    this._listeners.get(event)!.add(listener as unknown as EventHandler);
    return this;
  }

  once<K extends string & keyof Events>(event: K, listener: (...args: Events[K]) => void): this {
    const wrapper = (...args: Events[K]) => {
      this.off(event, wrapper as unknown as (...args: Events[K]) => void);
      listener(...args);
    };
    return this.on(event, wrapper as unknown as (...args: Events[K]) => void);
  }

  off<K extends string & keyof Events>(event: K, listener: (...args: Events[K]) => void): this {
    const handlers = this._listeners.get(event);
    if (handlers) {
      handlers.delete(listener as unknown as EventHandler);
      if (handlers.size === 0) {
        this._listeners.delete(event);
      }
    }
    return this;
  }

  emit<K extends string & keyof Events>(event: K, ...args: Events[K]): boolean {
    const handlers = this._listeners.get(event);
    if (!handlers || handlers.size === 0) return false;
    for (const handler of handlers) {
      handler(...(args as unknown as never[]));
    }
    return true;
  }

  removeAllListeners(event?: string): this {
    if (event) {
      this._listeners.delete(event);
    } else {
      this._listeners.clear();
    }
    return this;
  }

  listenerCount(event: string): number {
    return this._listeners.get(event)?.size ?? 0;
  }
}
