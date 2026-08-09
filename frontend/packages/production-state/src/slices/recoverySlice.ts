import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
  ProductionRecoverySnapshot,
  RecoveryStatus,
  ThreeWayDiffResultDTO,
} from '@windagent/production-contracts';

export interface RecoverySliceState {
  status: RecoveryStatus;
  activeSnapshot: ProductionRecoverySnapshot | null;
  staleDraft: {
    clientBaseRevision: string;
    serverCurrentRevision: string;
    serverCurrentSequence: number;
  } | null;
  conflictContext: ThreeWayDiffResultDTO | null;
  isOffline: boolean;
  lastSavedAt: string | null;
  errorMessage: string | null;
}

const initialState: RecoverySliceState = {
  status: 'IDLE',
  activeSnapshot: null,
  staleDraft: null,
  conflictContext: null,
  isOffline: false,
  lastSavedAt: null,
  errorMessage: null,
};

export const recoverySlice = createSlice({
  name: 'recovery',
  initialState,
  reducers: {
    setSaving(state) {
      state.status = 'SAVING';
    },
    saveRecoverySnapshot(state, action: PayloadAction<ProductionRecoverySnapshot>) {
      state.activeSnapshot = action.payload;
      state.status = 'SAVING';
      state.lastSavedAt = new Date().toISOString();
      state.errorMessage = null;
    },
    snapshotSavedSuccess(state) {
      state.status = 'IDLE';
    },
    restoreSnapshot(state, action: PayloadAction<ProductionRecoverySnapshot>) {
      state.activeSnapshot = action.payload;
      state.status = 'RECOVERED';
      state.errorMessage = null;
    },
    markStaleDraftDetected(
      state,
      action: PayloadAction<{
        clientBaseRevision: string;
        serverCurrentRevision: string;
        serverCurrentSequence: number;
      }>
    ) {
      state.status = 'STALE_DRAFT_DETECTED';
      state.staleDraft = action.payload;
    },
    clearCorruptSnapshot(state, action: PayloadAction<string>) {
      state.activeSnapshot = null;
      state.status = 'CORRUPT_CLEARED';
      state.errorMessage = action.payload;
    },
    setOfflineStatus(state, action: PayloadAction<boolean>) {
      state.isOffline = action.payload;
      if (action.payload) {
        state.status = 'OFFLINE_READ_ONLY';
      } else if (state.status === 'OFFLINE_READ_ONLY') {
        state.status = 'IDLE';
      }
    },
    transitionToConflict(state, action: PayloadAction<ThreeWayDiffResultDTO>) {
      state.status = 'CONFLICT';
      state.conflictContext = action.payload;
    },
    clearConflict(state) {
      state.status = 'IDLE';
      state.conflictContext = null;
      state.staleDraft = null;
    },
    clearRecovery(state) {
      state.status = 'IDLE';
      state.activeSnapshot = null;
      state.staleDraft = null;
      state.conflictContext = null;
      state.errorMessage = null;
    },
  },
});

export const {
  setSaving,
  saveRecoverySnapshot,
  snapshotSavedSuccess,
  restoreSnapshot,
  markStaleDraftDetected,
  clearCorruptSnapshot,
  setOfflineStatus,
  transitionToConflict,
  clearConflict,
  clearRecovery,
} = recoverySlice.actions;

export default recoverySlice.reducer;
