import { create } from "zustand";

export interface ConnectionStatusState {
  status: "idle" | "connecting" | "connected" | "offline";
  setStatus: (status: ConnectionStatusState["status"]) => void;
}

/**
 * UI/transport state that is not server state.  Realtime sync writes here so
 * components observe connection health without a query round-trip.
 */
export const useConnectionStatus = create<ConnectionStatusState>()((set) => ({
  status: "idle",
  setStatus: (status) => set({ status }),
}));
