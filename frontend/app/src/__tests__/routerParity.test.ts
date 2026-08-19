import { describe, it, expect } from 'vitest';
import {
  CANONICAL_ROUTE_MANIFEST,
  findRouteByPath,
  findRouteById,
  getNavigationGroups,
} from '../app/routeManifest';

describe('Phase 14 Router Parity & Deep Linking', () => {
  it('defines all 22+ canonical routes across studio and system groups', () => {
    expect(CANONICAL_ROUTE_MANIFEST.length).toBeGreaterThanOrEqual(20);

    const routeIds = CANONICAL_ROUTE_MANIFEST.map((r) => r.id);
    expect(routeIds).toContain('dashboard');
    expect(routeIds).toContain('studio');
    expect(routeIds).toContain('projects');
    expect(routeIds).toContain('project-detail');
    expect(routeIds).toContain('episodes');
    expect(routeIds).toContain('episode-workspace');
    expect(routeIds).toContain('storyboard');
    expect(routeIds).toContain('characters');
    expect(routeIds).toContain('world');
    expect(routeIds).toContain('assets');
    expect(routeIds).toContain('reviews');
    expect(routeIds).toContain('live-record');
    expect(routeIds).toContain('episode-production');
    expect(routeIds).toContain('production-script');
    expect(routeIds).toContain('production-assets');
    expect(routeIds).toContain('production-video');
    expect(routeIds).toContain('workspace');
    expect(routeIds).toContain('router');
    expect(routeIds).toContain('browser');
    expect(routeIds).toContain('files');
    expect(routeIds).toContain('settings');
    expect(routeIds).toContain('agents');
    expect(routeIds).toContain('workflows');
    expect(routeIds).toContain('monitoring');
    expect(routeIds).toContain('logs');
    expect(routeIds).toContain('memory');
    expect(routeIds).toContain('models-library');
    expect(routeIds).toContain('models-endpoints');
  });

  it('matches paths and aliases accurately', () => {
    // Root and dashboard
    expect(findRouteByPath('/')?.route.id).toBe('dashboard');
    expect(findRouteByPath('/dashboard')?.route.id).toBe('dashboard');
    expect(findRouteByPath('#/dashboard')?.route.id).toBe('dashboard');

    // Studio & projects
    expect(findRouteByPath('/studio')?.route.id).toBe('studio');
    expect(findRouteByPath('/studio/home')?.route.id).toBe('studio');
    expect(findRouteByPath('/projects')?.route.id).toBe('projects');
    expect(findRouteByPath('/studio/projects')?.route.id).toBe('projects');
    expect(findRouteByPath('/live-record')?.route.id).toBe('live-record');
    expect(findRouteByPath('/record')?.route.id).toBe('live-record');
    expect(findRouteByPath('/live')?.route.id).toBe('live-record');

    // Parameterized routes
    const projMatch = findRouteByPath('/projects/proj-alpha-99');
    expect(projMatch?.route.id).toBe('project-detail');
    expect(projMatch?.params.projectId).toBe('proj-alpha-99');

    const epMatch = findRouteByPath('/episodes/ep-007');
    expect(epMatch?.route.id).toBe('episode-workspace');
    expect(epMatch?.params.episodeId).toBe('ep-007');

    const wsMatch = findRouteByPath('/workspace/conv-456');
    expect(wsMatch?.route.id).toBe('workspace');
    expect(wsMatch?.params.conversationId).toBe('conv-456');

    // System routes & aliases
    expect(findRouteByPath('/routing')?.route.id).toBe('router');
    expect(findRouteByPath('/providers')?.route.id).toBe('models-endpoints');
    expect(findRouteByPath('/database')?.route.id).toBe('memory');
    expect(findRouteByPath('/memory')?.route.id).toBe('memory');
    expect(findRouteByPath('/browser')?.route.id).toBe('browser');
    expect(findRouteByPath('/files')?.route.id).toBe('files');
    expect(findRouteByPath('/settings')?.route.id).toBe('settings');
    expect(findRouteByPath('/logs')?.route.id).toBe('logs');
  });

  it('provides structured navigation groups for sidebar parity', () => {
    const groups = getNavigationGroups();
    expect(groups).toHaveLength(2);

    const studioGroup = groups.find((g) => g.id === 'studio');
    const systemGroup = groups.find((g) => g.id === 'system');

    expect(studioGroup).toBeDefined();
    expect(systemGroup).toBeDefined();
    expect(studioGroup!.items.length).toBeGreaterThan(0);
    expect(systemGroup!.items.length).toBeGreaterThan(0);
  });

  it('can look up any route descriptor by id', () => {
    const r = findRouteById('workspace');
    expect(r?.label).toBe('Agent Workspace');
    expect(r?.group).toBe('system');
  });
});
