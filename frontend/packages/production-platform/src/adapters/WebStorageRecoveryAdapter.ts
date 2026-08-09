import { IStateRecoveryStorageAdapter } from '../types';

export class WebStorageRecoveryAdapter implements IStateRecoveryStorageAdapter {
  private memoryFallback: Map<string, string> = new Map();

  async getItem(key: string): Promise<string | null> {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        return window.localStorage.getItem(key);
      }
    } catch {
      // Fallback if localStorage access is denied or restricted
    }
    return this.memoryFallback.get(key) || null;
  }

  async setItem(key: string, value: string): Promise<void> {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(key, value);
        return;
      }
    } catch {
      // Fallback to memory store if quota exceeded or disabled
    }
    this.memoryFallback.set(key, value);
  }

  async removeItem(key: string): Promise<void> {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.removeItem(key);
      }
    } catch {
      // Ignored
    }
    this.memoryFallback.delete(key);
  }

  async clear(): Promise<void> {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.clear();
      }
    } catch {
      // Ignored
    }
    this.memoryFallback.clear();
  }
}
