import { IStateRecoveryStorageAdapter } from '../types';

export class DesktopStorageRecoveryAdapter implements IStateRecoveryStorageAdapter {
  private localStore: Map<string, string> = new Map();

  async getItem(key: string): Promise<string | null> {
    return this.localStore.get(key) || null;
  }

  async setItem(key: string, value: string): Promise<void> {
    this.localStore.set(key, value);
  }

  async removeItem(key: string): Promise<void> {
    this.localStore.delete(key);
  }

  async clear(): Promise<void> {
    this.localStore.clear();
  }
}
