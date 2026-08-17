import { describe, it, expect } from 'vitest';
import {
  CANONICAL_ROUTE_MANIFEST,
  findRouteByPath,
  findRouteById,
  getNavigationGroups,
} from '../app/routeManifest';

describe('Canonical Route Manifest & Matcher', () => {
  it('contains essential canonical routes for studio and system groups', () => {
    expect(CANONICAL_ROUTE_MANIFEST.length).toBeGreaterThanOrEqual(15);
    const ids = CANONICAL_ROUTE_MANIFEST.map((r) => r.id);
    expect(ids).toContain('dashboard');
    expect(ids).toContain('studio');
    expect(ids).toContain('projects');
    expect(ids).toContain('episodes');
    expect(ids).toContain('assets');
    expect(ids).toContain('workspace');
    expect(ids).toContain('settings');
    expect(ids).toContain('agents');
  });

  it('matches exact canonical path', () => {
    const matched = findRouteByPath('/dashboard');
    expect(matched).not.toBeNull();
    expect(matched?.route.id).toBe('dashboard');
  });

  it('matches alias paths (e.g. root / maps to dashboard)', () => {
    const matchedRoot = findRouteByPath('/');
    expect(matchedRoot?.route.id).toBe('dashboard');

    const matchedEmpty = findRouteByPath('');
    expect(matchedEmpty?.route.id).toBe('dashboard');

    const matchedLegacyAssets = findRouteByPath('/asset-library');
    expect(matchedLegacyAssets?.route.id).toBe('assets');

    const matchedStudioProjects = findRouteByPath('/studio/projects');
    expect(matchedStudioProjects?.route.id).toBe('projects');
  });

  it('extracts route path parameters correctly', () => {
    const matchedProject = findRouteByPath('/studio/projects/proj-alpha-123');
    expect(matchedProject).not.toBeNull();
    expect(matchedProject?.route.id).toBe('project-detail');
    expect(matchedProject?.params.projectId).toBe('proj-alpha-123');


    const matchedWorkspace = findRouteByPath('/workspace/conv-test-999');
    expect(matchedWorkspace).not.toBeNull();
    expect(matchedWorkspace?.route.id).toBe('workspace');
    expect(matchedWorkspace?.params.conversationId).toBe('conv-test-999');
  });

  it('finds route by ID', () => {
    const route = findRouteById('workspace');
    expect(route).toBeDefined();
    expect(route?.group).toBe('system');
    expect(route?.label).toBe('Agent Workspace');
  });

  it('generates navigation groups for AppShell sidebar', () => {
    const groups = getNavigationGroups();
    expect(groups).toHaveLength(2);
    expect(groups[0].id).toBe('studio');
    expect(groups[1].id).toBe('system');

    const studioItemIds = groups[0].items.map((i) => i.id);
    expect(studioItemIds).toContain('dashboard');
    expect(studioItemIds).toContain('studio');
    expect(studioItemIds).toContain('projects');

    const systemItemIds = groups[1].items.map((i) => i.id);
    expect(systemItemIds).toContain('workspace');
    expect(systemItemIds).toContain('settings');
  });

  it('returns null for unknown paths', () => {
    const matched = findRouteByPath('/some/completely/unknown/deep/path');
    expect(matched).toBeNull();
  });
});
