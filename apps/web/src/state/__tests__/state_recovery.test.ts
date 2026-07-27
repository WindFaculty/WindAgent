/**
 * Tests for StateRecoveryEngine - Session state persistence and recovery.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { StateRecoveryEngine, AppStateSnapshot } from "../state_recovery";

const mockLocalStorage = {
  store: {} as Record<string, string>,
  getItem(key: string): string | null {
    return this.store[key] || null;
  },
  setItem(key: string, value: string): void {
    this.store[key] = value;
  },
  removeItem(key: string): void {
    delete this.store[key];
  },
  clear(): void {
    this.store = {};
  },
};

Object.defineProperty(global, "localStorage", {
  value: mockLocalStorage,
  writable: true,
});

describe("StateRecoveryEngine", () => {
  let engine: StateRecoveryEngine;

  beforeEach(() => {
    mockLocalStorage.clear();
    engine = new StateRecoveryEngine();
  });

  afterEach(() => {
    mockLocalStorage.clear();
    vi.resetAllMocks();
  });

  describe("getDefaultSnapshot", () => {
    it("should return default snapshot with correct values", () => {
      const snapshot = engine.getDefaultSnapshot();

      expect(snapshot.activeTab).toBe("overview");
      expect(snapshot.activeTaskId).toBeNull();
      expect(snapshot.pendingPermissions).toEqual([]);
      expect(snapshot.isWorkerDisconnected).toBe(false);
      expect(snapshot.lastSyncTimestamp).toBeTypeOf("number");
    });
  });

  describe("saveSnapshot and loadSnapshot", () => {
    it("should save and load snapshot correctly", () => {
      const snapshot: AppStateSnapshot = {
        activeTab: "tasks",
        activeTaskId: "task-123",
        pendingPermissions: [{ id: "perm-1", action: "execute", target: "tool:shell" }],
        isWorkerDisconnected: true,
        lastSyncTimestamp: 1234567890,
      };

      engine.saveSnapshot(snapshot);
      const loaded = engine.loadSnapshot();

      expect(loaded).toEqual(snapshot);
    });

    it("should return default snapshot when localStorage is empty", () => {
      const loaded = engine.loadSnapshot();
      expect(loaded).toEqual(engine.getDefaultSnapshot());
    });

    it("should return default snapshot when localStorage has invalid JSON", () => {
      mockLocalStorage.setItem("windagent_web_state_v2", "invalid json");

      const loaded = engine.loadSnapshot();
      const defaultSnapshot = engine.getDefaultSnapshot();
      expect(loaded.activeTab).toBe(defaultSnapshot.activeTab);
      expect(loaded.activeTaskId).toBe(defaultSnapshot.activeTaskId);
      expect(loaded.pendingPermissions).toEqual(defaultSnapshot.pendingPermissions);
      expect(loaded.isWorkerDisconnected).toBe(defaultSnapshot.isWorkerDisconnected);
    });

    it("should return default snapshot when localStorage key does not exist", () => {
      mockLocalStorage.removeItem("windagent_web_state_v2");

      const loaded = engine.loadSnapshot();
      expect(loaded).toEqual(engine.getDefaultSnapshot());
    });

    it("should overwrite existing snapshot", () => {
      const snapshot1: AppStateSnapshot = {
        activeTab: "overview",
        activeTaskId: "task-1",
        pendingPermissions: [],
        isWorkerDisconnected: false,
        lastSyncTimestamp: 1000,
      };
      const snapshot2: AppStateSnapshot = {
        activeTab: "providers",
        activeTaskId: "task-2",
        pendingPermissions: [{ id: "p1", action: "read", target: "file" }],
        isWorkerDisconnected: true,
        lastSyncTimestamp: 2000,
      };

      engine.saveSnapshot(snapshot1);
      engine.saveSnapshot(snapshot2);
      const loaded = engine.loadSnapshot();

      expect(loaded).toEqual(snapshot2);
    });
  });

  describe("clearSnapshot", () => {
    it("should clear snapshot and return default on next load", () => {
      const snapshot: AppStateSnapshot = {
        activeTab: "tasks",
        activeTaskId: "task-1",
        pendingPermissions: [],
        isWorkerDisconnected: false,
        lastSyncTimestamp: Date.now(),
      };

      engine.saveSnapshot(snapshot);
      engine.clearSnapshot();
      const loaded = engine.loadSnapshot();

      expect(loaded).toEqual(engine.getDefaultSnapshot());
    });
  });

  describe("pendingPermissions handling", () => {
    it("should persist and restore pending permissions", () => {
      const snapshot: AppStateSnapshot = {
        activeTab: "overview",
        activeTaskId: null,
        pendingPermissions: [
          { id: "perm-1", action: "execute", target: "tool:shell" },
          { id: "perm-2", action: "delete", target: "file:/important" },
        ],
        isWorkerDisconnected: false,
        lastSyncTimestamp: Date.now(),
      };

      engine.saveSnapshot(snapshot);
      const loaded = engine.loadSnapshot();

      expect(loaded.pendingPermissions).toHaveLength(2);
      expect(loaded.pendingPermissions[0].id).toBe("perm-1");
      expect(loaded.pendingPermissions[1].action).toBe("delete");
    });

    it("should handle empty pending permissions", () => {
      const snapshot: AppStateSnapshot = {
        ...engine.getDefaultSnapshot(),
        pendingPermissions: [],
      };

      engine.saveSnapshot(snapshot);
      const loaded = engine.loadSnapshot();

      expect(loaded.pendingPermissions).toEqual([]);
    });
  });

  describe("worker disconnected state", () => {
    it("should persist worker disconnected state", () => {
      const snapshot: AppStateSnapshot = {
        ...engine.getDefaultSnapshot(),
        isWorkerDisconnected: true,
      };

      engine.saveSnapshot(snapshot);
      const loaded = engine.loadSnapshot();

      expect(loaded.isWorkerDisconnected).toBe(true);
    });

    it("should persist active task id", () => {
      const snapshot: AppStateSnapshot = {
        ...engine.getDefaultSnapshot(),
        activeTaskId: "task-active-123",
      };

      engine.saveSnapshot(snapshot);
      const loaded = engine.loadSnapshot();

      expect(loaded.activeTaskId).toBe("task-active-123");
    });
  });

  describe("edge cases", () => {
    it("should handle missing localStorage gracefully (SSR)", () => {
      const originalLocalStorage = global.localStorage;
      // @ts-ignore
      delete global.localStorage;

      const engine2 = new StateRecoveryEngine();
      const snapshot = engine2.loadSnapshot();

      expect(snapshot).toEqual(engine2.getDefaultSnapshot());

      global.localStorage = originalLocalStorage;
    });

    it("should handle localStorage quota exceeded", () => {
      const snapshot: AppStateSnapshot = {
        ...engine.getDefaultSnapshot(),
        pendingPermissions: Array(1000).fill({ id: "x", action: "y", target: "z" }),
      };

      mockLocalStorage.setItem = vi.fn(() => {
        throw new Error("QuotaExceededError");
      });

      expect(() => engine.saveSnapshot(snapshot)).not.toThrow();
    });
  });
});