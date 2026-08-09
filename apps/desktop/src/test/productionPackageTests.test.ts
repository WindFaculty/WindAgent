import { describe, it, expect } from 'vitest';
import {
  FakeTestAdapter,
  BrowserWebAdapter,
  TauriDesktopAdapter,
  CancelledError,
  UnsupportedError,
} from '../../../../frontend/packages/production-platform/src';
import {
  createProductionStore,
  switchProject,
  setActivePage,
  setSyncStatus,
  resetContext,
  checkUnsavedChangesGuard,
} from '../../../../frontend/packages/production-state/src';
import { FakeProductionApiClient } from '../../../../frontend/packages/production-client/src';
import {
  ProductionRouteCodec,
  ProductionRoute,
} from '../../../../frontend/packages/production-contracts/src';

describe('Shared Production Packages Integration & Unit Tests', () => {
  describe('Production Platform Adapters & Boundaries', () => {
    it('FakeTestAdapter handles successful file selection and capabilities', async () => {
      const adapter = new FakeTestAdapter();
      expect(adapter.supportsLocalFilesystem()).toBe(true);

      const files = await adapter.selectLocalFile();
      expect(files.length).toBe(1);
      expect(files[0].name).toBe('screenplay_v1.fountain');
    });

    it('FakeTestAdapter handles user cancellation cleanly with CancelledError', async () => {
      const adapter = new FakeTestAdapter();
      adapter.shouldFailCancel = true;

      await expect(adapter.selectLocalFile()).rejects.toThrow(CancelledError);
    });

    it('BrowserWebAdapter reports no native local filesystem support', () => {
      const adapter = new BrowserWebAdapter();
      expect(adapter.supportsLocalFilesystem()).toBe(false);
    });

    it('BrowserWebAdapter throws UnsupportedError when revealFile is called', async () => {
      const adapter = new BrowserWebAdapter();
      await expect(adapter.revealFile('art-1')).rejects.toThrow(UnsupportedError);
    });

    it('TauriDesktopAdapter reports local filesystem support', () => {
      const adapter = new TauriDesktopAdapter();
      expect(adapter.supportsLocalFilesystem()).toBe(true);
    });
  });

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

  describe('Production Navigation & Routing Codec', () => {
    it('parses valid production URL into typed ProductionRoute object', () => {
      const route = ProductionRouteCodec.parseRoute('/production/proj-alpha/script?entityId=scene-101');
      expect(route).not.toBeNull();
      expect(route?.projectId).toBe('proj-alpha');
      expect(route?.page).toBe('script');
      expect(route?.entityId).toBe('scene-101');
    });

    it('stringifies ProductionRoute object back into standard URL path', () => {
      const routeObj: ProductionRoute = {
        projectId: 'proj-beta',
        page: 'assets',
        entityId: 'asset-mesh-42',
        revisionId: 'rev-v2',
      };

      const path = ProductionRouteCodec.stringifyRoute(routeObj);
      expect(path).toBe('/production/proj-beta/assets?entityId=asset-mesh-42&revisionId=rev-v2');
    });

    it('handles invalid path gracefully by returning null', () => {
      const route = ProductionRouteCodec.parseRoute('/other/path');
      expect(route).toBeNull();
    });

    it('handles route round-trip with special encoded characters', () => {
      const original: ProductionRoute = {
        projectId: 'proj with spaces',
        page: 'video',
        entityId: 'shot #12',
      };

      const url = ProductionRouteCodec.stringifyRoute(original);
      const decoded = ProductionRouteCodec.parseRoute(url);

      expect(decoded?.projectId).toBe('proj with spaces');
      expect(decoded?.page).toBe('video');
      expect(decoded?.entityId).toBe('shot #12');
    });
  });
});
