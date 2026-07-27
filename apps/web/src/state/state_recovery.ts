/**
 * State Recovery & Reconnect Engine for WindAgent Web Application (Phase 13).
 * Manages refresh recovery, pending permissions restoration, and worker connection states.
 */

export interface AppStateSnapshot {
  activeTab: string;
  activeTaskId: string | null;
  pendingPermissions: Array<{ id: string; action: string; target: string }>;
  isWorkerDisconnected: boolean;
  lastSyncTimestamp: number;
}

export class StateRecoveryEngine {
  private storageKey: string = "windagent_web_state_v2";

  saveSnapshot(snapshot: AppStateSnapshot): void {
    if (typeof localStorage !== "undefined") {
      try {
        localStorage.setItem(this.storageKey, JSON.stringify(snapshot));
      } catch (e) {
        console.warn("Failed to save state snapshot:", e);
      }
    }
  }

  loadSnapshot(): AppStateSnapshot {
    if (typeof localStorage !== "undefined") {
      const raw = localStorage.getItem(this.storageKey);
      if (raw) {
        try {
          return JSON.parse(raw);
        } catch (e) {
          console.warn("Failed to parse state snapshot, using default fallback.");
        }
      }
    }
    return this.getDefaultSnapshot();
  }

  getDefaultSnapshot(): AppStateSnapshot {
    return {
      activeTab: "overview",
      activeTaskId: null,
      pendingPermissions: [],
      isWorkerDisconnected: false,
      lastSyncTimestamp: Date.now(),
    };
  }

  clearSnapshot(): void {
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem(this.storageKey);
    }
  }
}
