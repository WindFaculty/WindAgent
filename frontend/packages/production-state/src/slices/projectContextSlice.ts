import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';
import {
  ProjectStatus,
  RevisionStatus,
  SyncStatus,
  BackendStatus,
  ProductionPage,
  SelectedEntity,
  ProductionProject,
  ProductionRevision,
} from '@windagent/production-contracts';
import { ProductionApiClient } from '@windagent/production-client';

export interface ProductionProjectContextState {
  projectId: string | null;
  projectStatus: ProjectStatus;
  projectDetails: ProductionProject | null;
  revisionId: string | null;
  revisionStatus: RevisionStatus;
  revisionDetails: ProductionRevision | null;
  screenplayId: string | null;
  currentSequence: number | null;
  activePage: ProductionPage;
  selectedEntity: SelectedEntity | null;
  syncStatus: SyncStatus;
  backendStatus: BackendStatus;
  errorMessage: string | null;
}

const initialState: ProductionProjectContextState = {
  projectId: null,
  projectStatus: 'idle',
  projectDetails: null,
  revisionId: null,
  revisionStatus: 'draft',
  revisionDetails: null,
  screenplayId: null,
  currentSequence: null,
  activePage: 'script',
  selectedEntity: null,
  syncStatus: 'synced',
  backendStatus: 'online',
  errorMessage: null,
};

export const switchProject = createAsyncThunk(
  'projectContext/switchProject',
  async (
    { projectId, client }: { projectId: string; client: ProductionApiClient },
    { rejectWithValue }
  ) => {
    try {
      const project = await client.getProject(projectId);
      if (!project) throw new Error(`Project ${projectId} not found`);

      const revision = await client.getLatestRevision(projectId);
      return { project, revision };
    } catch (err) {
      return rejectWithValue((err as Error).message);
    }
  }
);

export const projectContextSlice = createSlice({
  name: 'projectContext',
  initialState,
  reducers: {
    setActivePage(state, action: PayloadAction<ProductionPage>) {
      state.activePage = action.payload;
    },
    setSelectedEntity(state, action: PayloadAction<SelectedEntity | null>) {
      state.selectedEntity = action.payload;
    },
    setSyncStatus(state, action: PayloadAction<SyncStatus>) {
      state.syncStatus = action.payload;
    },
    setBackendStatus(state, action: PayloadAction<BackendStatus>) {
      state.backendStatus = action.payload;
    },
    resetContext(state) {
      Object.assign(state, initialState);
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(switchProject.pending, (state) => {
        state.projectStatus = 'loading';
        state.errorMessage = null;
      })
      .addCase(switchProject.fulfilled, (state, action) => {
        state.projectId = action.payload.project.id;
        state.projectDetails = action.payload.project;
        state.projectStatus = 'ready';
        state.revisionId = action.payload.revision ? action.payload.revision.id : null;
        state.revisionDetails = action.payload.revision;
        state.revisionStatus = action.payload.revision ? action.payload.revision.status : 'draft';
        state.selectedEntity = null;
        state.syncStatus = 'synced';
        state.errorMessage = null;
      })
      .addCase(switchProject.rejected, (state, action) => {
        state.projectStatus = 'error';
        state.errorMessage = (action.payload as string) || 'Failed to switch project';
      });
  },
});

export const {
  setActivePage,
  setSelectedEntity,
  setSyncStatus,
  setBackendStatus,
  resetContext,
} = projectContextSlice.actions;

export const selectProjectContext = (state: { projectContext: ProductionProjectContextState }) =>
  state.projectContext;
