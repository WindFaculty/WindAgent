/**
 * UI State Management Store.
 * Implements standard Zustand-compatible interface using React's useSyncExternalStore (P4.9).
 * Strictly scoped to local UI presentation state.
 */

import { useSyncExternalStore } from 'react';
import type { MetricState } from '@windagent/studio-shell';

export interface UIState {
  sidebarCollapsed: boolean;
  refreshInterval: string;
  conversationId: string;
  hermesOnline: boolean | null;
  backendOnline: boolean | null;
  metrics: MetricState;

  // Actions
  setSidebarCollapsed: (collapsed: boolean | ((prev: boolean) => boolean)) => void;
  setRefreshInterval: (interval: string) => void;
  setConversationId: (id: string) => void;
  setBackendOnline: (online: boolean | null) => void;
  setHermesOnline: (online: boolean | null) => void;
  setMetrics: (metrics: MetricState | ((prev: MetricState) => MetricState)) => void;
}

function getInitialConversationId(): string {
  if (typeof sessionStorage !== 'undefined') {
    const existing = sessionStorage.getItem('windagent.conversationId');
    if (existing) return existing;
    const fresh =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `conv-${Date.now()}`;
    sessionStorage.setItem('windagent.conversationId', fresh);
    return fresh;
  }
  return 'conv-default';
}

type SetStateFn<T> = (partial: Partial<T> | ((state: T) => Partial<T>)) => void;

function createStore<T extends object>(initializer: (set: SetStateFn<T>) => T) {
  let state: T;
  const listeners = new Set<() => void>();

  const setState: SetStateFn<T> = (partial) => {
    const next = typeof partial === 'function' ? (partial as (state: T) => Partial<T>)(state) : partial;
    state = { ...state, ...next };
    listeners.forEach((l) => l());
  };

  state = initializer(setState);

  const subscribe = (listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  };

  const getState = () => state;

  function useStore<U = T>(selector: (s: T) => U = (s) => s as unknown as U): U {
    return useSyncExternalStore(subscribe, () => selector(state), () => selector(state));
  }

  useStore.getState = getState;
  useStore.setState = setState;
  useStore.subscribe = subscribe;

  return useStore;
}

export const useUIStore = createStore<UIState>((set) => ({
  sidebarCollapsed: false,
  refreshInterval: '10s',
  conversationId: getInitialConversationId(),
  hermesOnline: null,
  backendOnline: null,
  metrics: {
    cpu: 18,
    ram: 61,
    ramGb: 9.7,
    ramTotalGb: 16,
    gpu: 28,
    gpuName: 'NVIDIA GPU',
    vram: 42,
    vramGb: 6.7,
    vramTotalGb: 16,
    cpuHistory: [15, 18, 16, 21, 19, 18],
    ramHistory: [60, 61, 61, 61, 61, 61],
    gpuHistory: [25, 30, 26, 29, 27, 28],
    vramHistory: [42, 42, 42, 42, 42, 42],
  },

  setSidebarCollapsed: (collapsed) =>
    set((state) => ({
      sidebarCollapsed: typeof collapsed === 'function' ? collapsed(state.sidebarCollapsed) : collapsed,
    })),
  setRefreshInterval: (refreshInterval) => set({ refreshInterval }),
  setConversationId: (conversationId) => set({ conversationId }),
  setBackendOnline: (backendOnline) => set({ backendOnline }),
  setHermesOnline: (hermesOnline) => set({ hermesOnline }),
  setMetrics: (metrics) =>
    set((state) => ({
      metrics: typeof metrics === 'function' ? metrics(state.metrics) : metrics,
    })),
}));
