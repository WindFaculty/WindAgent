import { describe, it, expect } from 'vitest';
import { ProductionRouteCodec, ProductionRoute } from '@windagent/production-contracts';

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
