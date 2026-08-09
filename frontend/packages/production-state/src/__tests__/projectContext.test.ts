import { describe, it, expect } from 'vitest';
import { createProductionStore } from '../store';
import { switchProject, setActivePage, setSyncStatus, resetContext } from '../slices/projectContextSlice';
import { FakeProductionApiClient } from '@windagent/production-client';
import { checkUnsavedChangesGuard } from '../hooks/useUnsavedChangesGuard';

describe('Production Project Context State', () => {
  it('initializes with idle context and default values', () => {
    const store = createProductionStore();
    const state = store.getState().projectContext;

    expect(state.projectId).toBeNull();
    expect(state.projectStatus).toBe('idle');
    expect(state.activePage).toBe('script');
    expect(state.syncStatus).toBe('synced');
  });

  it('switches project successfully via API client', async () => {
    const store = createProductionStore();
    const client = new FakeProductionApiClient();

    await store.dispatch(switchProject({ projectId: 'proj-alpha', client }));
    const state = store.getState().projectContext;

    expect(state.projectId).toBe('proj-alpha');
    expect(state.projectStatus).toBe('ready');
    expect(state.projectDetails?.name).toBe('Alpha Production Project');
    expect(state.revisionId).toBe('rev-proj-alpha-v1');
  });

  it('handles missing project gracefully with error state', async () => {
    const store = createProductionStore();
    const client = new FakeProductionApiClient();

    await store.dispatch(switchProject({ projectId: 'non-existent', client }));
    const state = store.getState().projectContext;

    expect(state.projectStatus).toBe('error');
    expect(state.errorMessage).toContain('non-existent not found');
  });

  it('prevents navigation when dirty unsaved changes exist', () => {
    const canLeaveUnsaved = checkUnsavedChangesGuard('unsaved', () => false);
    expect(canLeaveUnsaved).toBe(false);

    const canLeaveSynced = checkUnsavedChangesGuard('synced', () => false);
    expect(canLeaveSynced).toBe(true);
  });

  it('resets context properly', () => {
    const store = createProductionStore();
    store.dispatch(setActivePage('video'));
    store.dispatch(setSyncStatus('unsaved'));

    store.dispatch(resetContext());
    const state = store.getState().projectContext;

    expect(state.activePage).toBe('script');
    expect(state.syncStatus).toBe('synced');
  });
});
