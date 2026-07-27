/**
 * Tests for App component - Application bootstrap and state recovery.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { App } from "../App";

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

describe("App Component", () => {
  beforeEach(() => {
    mockLocalStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    mockLocalStorage.clear();
    vi.restoreAllMocks();
  });

  describe("bootstrap", () => {
    it("should render without crashing", () => {
      render(<App />);
      expect(screen.getByText("WindAgent V2 Architecture - Web Portal")).toBeInTheDocument();
    });

    it("should render all navigation tabs", () => {
      render(<App />);
      expect(screen.getByText("OVERVIEW")).toBeInTheDocument();
      expect(screen.getByText("TASKS")).toBeInTheDocument();
      expect(screen.getByText("WORKFLOWS")).toBeInTheDocument();
      expect(screen.getByText("PROVIDERS")).toBeInTheDocument();
      expect(screen.getByText("EVALS")).toBeInTheDocument();
    });

    it("should have active tab highlighted by default", () => {
      render(<App />);
      const overviewBtn = screen.getByText("OVERVIEW");
      expect(overviewBtn).toHaveStyle("background-color: #3b82f6");
    });

    it("should display state recovery info", () => {
      render(<App />);
      expect(screen.getByText(/State Recovery: Active tab restored from snapshot/)).toBeInTheDocument();
    });
  });

  describe("tab switching", () => {
    it("should switch active tab on click", () => {
      render(<App />);

      const tasksBtn = screen.getByText("TASKS");
      fireEvent.click(tasksBtn);

      expect(tasksBtn).toHaveStyle("background-color: #3b82f6");
      expect(screen.getByText("OVERVIEW")).not.toHaveStyle("background-color: #3b82f6");
      expect(screen.getByText("Current View: TASKS")).toBeInTheDocument();
    });

    it("should persist active tab to localStorage", () => {
      render(<App />);

      const tasksBtn = screen.getByText("TASKS");
      fireEvent.click(tasksBtn);

      const stored = localStorage.getItem("windagent_web_state_v2");
      expect(stored).toBeTruthy();

      const parsed = JSON.parse(stored!);
      expect(parsed.activeTab).toBe("tasks");
    });

    it("should restore active tab from snapshot on mount", () => {
      const snapshot = {
        activeTab: "providers",
        activeTaskId: null,
        pendingPermissions: [],
        isWorkerDisconnected: false,
        lastSyncTimestamp: Date.now(),
      };
      localStorage.setItem("windagent_web_state_v2", JSON.stringify(snapshot));

      render(<App />);

      expect(screen.getByText("PROVIDERS")).toHaveStyle("background-color: #3b82f6");
      expect(screen.getByText("Current View: PROVIDERS")).toBeInTheDocument();
    });

    it("should update lastSyncTimestamp on tab change", () => {
      render(<App />);

      const before = Date.now();
      const tasksBtn = screen.getByText("TASKS");
      fireEvent.click(tasksBtn);
      const after = Date.now();

      const stored = localStorage.getItem("windagent_web_state_v2");
      const parsed = JSON.parse(stored!);
      expect(parsed.lastSyncTimestamp).toBeGreaterThanOrEqual(before);
      expect(parsed.lastSyncTimestamp).toBeLessThanOrEqual(after);
    });
  });

  describe("worker disconnected state", () => {
    it("should show warning when worker is disconnected", () => {
      const snapshot = {
        activeTab: "overview",
        activeTaskId: null,
        pendingPermissions: [],
        isWorkerDisconnected: true,
        lastSyncTimestamp: Date.now(),
      };
      localStorage.setItem("windagent_web_state_v2", JSON.stringify(snapshot));

      render(<App />);

      expect(screen.getByText(/Worker Disconnected! Attempting reconnect/)).toBeInTheDocument();
      expect(screen.getByText(/Worker Disconnected! Attempting reconnect/)).toHaveStyle("background-color: #ef4444");
    });

    it("should not show warning when worker is connected", () => {
      render(<App />);
      expect(screen.queryByText(/Worker Disconnected/)).not.toBeInTheDocument();
    });
  });

  describe("loading/error/empty states", () => {
    it("should render main content area", () => {
      render(<App />);
      expect(screen.getByText("Current View: OVERVIEW")).toBeInTheDocument();
    });

    it("should have proper styling for dark theme", () => {
      render(<App />);
      const mainDiv = document.body.querySelector('div[style*="min-height: 100vh"]');
      expect(mainDiv).toBeTruthy();
      expect(mainDiv!.getAttribute('style')).toContain('#0f172a');
    });
  });

  describe("event replay after reconnect", () => {
    it("should restore state correctly after remount", () => {
      const { unmount } = render(<App />);

      const tasksBtn = screen.getByText("TASKS");
      fireEvent.click(tasksBtn);

      unmount();

      render(<App />);

      expect(screen.getByText("TASKS")).toHaveStyle("background-color: #3b82f6");
      expect(screen.getByText("Current View: TASKS")).toBeInTheDocument();
    });
  });
});
