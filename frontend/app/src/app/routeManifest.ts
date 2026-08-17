/**
 * RouteManifest — Authoritative Single Source of Truth for Routing and Navigation (P4.5).
 */


export type NavigationGroupKey = 'studio' | 'system';

export interface RouteDescriptor {
  readonly id: string;
  readonly path: string;
  readonly aliases?: readonly string[];
  readonly label: string;
  readonly iconName?: string;
  readonly group: NavigationGroupKey;
  readonly badge?: string;
  readonly navigationVisible?: boolean;
  readonly breadcrumb?: string[];
  readonly capabilities?: readonly string[];
}

export const CANONICAL_ROUTE_MANIFEST: readonly RouteDescriptor[] = [
  // STUDIO GROUP
  {
    id: 'dashboard',
    path: '/dashboard',
    aliases: ['/', ''],
    label: 'Dashboard',
    iconName: 'LayoutDashboard',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Dashboard'],
  },
  {
    id: 'studio',
    path: '/studio',
    aliases: ['/studio/home'],
    label: 'Studio',
    iconName: 'Clapperboard',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Episode Studio'],
  },

  {
    id: 'projects',
    path: '/projects',
    aliases: ['/studio/projects'],
    label: 'Projects',
    iconName: 'Folder',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Projects'],
  },
  {
    id: 'project-detail',
    path: '/projects/:projectId',
    aliases: ['/studio/projects/:projectId'],
    label: 'Project Detail',
    iconName: 'Folder',
    group: 'studio',
    navigationVisible: false,
    breadcrumb: ['Studio', 'Projects', 'Detail'],
  },

  {
    id: 'episodes',
    path: '/episodes',
    aliases: ['/studio/episodes'],
    label: 'Episodes',
    iconName: 'Film',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Episodes'],
  },
  {
    id: 'episode-workspace',
    path: '/episodes/:episodeId',
    aliases: ['/studio/episodes/:episodeId'],
    label: 'Episode Workspace',
    iconName: 'Film',
    group: 'studio',
    navigationVisible: false,
    breadcrumb: ['Studio', 'Episodes', 'Workspace'],
  },

  {
    id: 'storyboard',
    path: '/storyboard',
    aliases: ['/studio/storyboard'],
    label: 'Story Board',
    iconName: 'LayoutGrid',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Story Board'],
  },
  {
    id: 'characters',
    path: '/characters',
    aliases: ['/studio/characters'],
    label: 'Characters',
    iconName: 'Users',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Characters'],
  },
  {
    id: 'world',
    path: '/world',
    aliases: ['/studio/world'],
    label: 'World / Setting',
    iconName: 'Globe',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'World'],
  },
  {
    id: 'assets',
    path: '/assets',
    aliases: ['/asset-library', '/production/assets'],
    label: 'Assets',
    iconName: 'Package',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Asset Library'],
  },
  {
    id: 'reviews',
    path: '/reviews',
    aliases: ['/studio/reviews'],
    label: 'Reviews',
    iconName: 'CheckSquare',
    group: 'studio',
    navigationVisible: true,
    breadcrumb: ['Studio', 'Reviews'],
  },
  {
    id: 'episode-production',
    path: '/episodes/:episodeId/production',
    aliases: ['/studio/episodes/:episodeId/production'],
    label: 'Episode Production',
    iconName: 'Clapperboard',
    group: 'studio',
    navigationVisible: false,
    breadcrumb: ['Studio', 'Episodes', 'Production'],
  },
  {
    id: 'production-script',
    path: '/production/script',
    aliases: ['/production'],
    label: 'Production Script',
    group: 'studio',
    navigationVisible: false,
    breadcrumb: ['Production', 'Script'],
  },
  {
    id: 'production-assets',
    path: '/production/assets',
    label: 'Production Assets',
    group: 'studio',
    navigationVisible: false,
    breadcrumb: ['Production', 'Assets'],
  },
  {
    id: 'production-video',
    path: '/production/video',
    label: 'Production Video',
    group: 'studio',
    navigationVisible: false,
    breadcrumb: ['Production', 'Video'],
  },

  // SYSTEM GROUP
  {
    id: 'workspace',
    path: '/workspace',
    aliases: ['/system/workspace', '/workspace/:conversationId'],
    label: 'Agent Workspace',
    iconName: 'Bot',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Agent Workspace'],
  },
  {
    id: 'router',
    path: '/router',
    aliases: ['/system/router'],
    label: 'Router / Providers',
    iconName: 'Server',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Router'],
  },
  {
    id: 'browser',
    path: '/browser',
    aliases: ['/system/browser'],
    label: 'Browser',
    iconName: 'Globe',
    badge: 'STUB',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Browser'],
  },
  {
    id: 'files',
    path: '/files',
    aliases: ['/system/files'],
    label: 'Files',
    iconName: 'Folder',
    badge: 'STUB',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Files'],
  },
  {
    id: 'settings',
    path: '/settings',
    aliases: ['/system/settings'],
    label: 'Settings',
    iconName: 'Settings',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Settings'],
  },
  {
    id: 'agents',
    path: '/agents',
    aliases: ['/system/agents'],
    label: 'Agents',
    iconName: 'Users',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Agents'],
  },
  {
    id: 'workflows',
    path: '/workflows',
    aliases: ['/system/workflows'],
    label: 'Workflows',
    iconName: 'GitBranch',
    badge: 'BETA',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Workflows'],
  },
  {
    id: 'monitoring',
    path: '/monitoring',
    aliases: ['/system/monitoring'],
    label: 'Monitoring',
    iconName: 'Activity',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Monitoring'],
  },
  {
    id: 'logs',
    path: '/logs',
    aliases: ['/system/logs'],
    label: 'Logs',
    iconName: 'FileText',
    group: 'system',
    navigationVisible: true,

    breadcrumb: ['System', 'Logs'],
  },
  {
    id: 'memory',
    path: '/memory',
    aliases: ['/database', '/system/memory'],
    label: 'Database',
    iconName: 'Database',
    badge: 'BETA',
    group: 'system',
    navigationVisible: true,
    breadcrumb: ['System', 'Database & Memory'],
  },
  {
    id: 'models-library',
    path: '/models',
    aliases: ['/models/library'],
    label: 'Models',
    group: 'system',
    navigationVisible: false,
    breadcrumb: ['System', 'Models'],
  },
  {
    id: 'models-endpoints',
    path: '/models/endpoints',
    label: 'Endpoints',
    group: 'system',
    navigationVisible: false,
    breadcrumb: ['System', 'Endpoints'],
  },
];

export function findRouteByPath(rawPath: string): { route: RouteDescriptor; params: Record<string, string> } | null {
  const normalized = rawPath.replace(/^#/, '').split('?')[0].trim() || '/';

  for (const item of CANONICAL_ROUTE_MANIFEST) {
    const patterns = [item.path, ...(item.aliases || [])];
    for (const pattern of patterns) {
      const match = matchPath(pattern, normalized);
      if (match) {
        return { route: item, params: match.params };
      }
    }
  }

  return null;
}

export function findRouteById(id: string): RouteDescriptor | undefined {
  return CANONICAL_ROUTE_MANIFEST.find((r) => r.id === id);
}

function matchPath(pattern: string, path: string): { params: Record<string, string> } | null {
  const patternParts = pattern.split('/').filter(Boolean);
  const pathParts = path.split('/').filter(Boolean);

  if (patternParts.length !== pathParts.length) {
    // Special root match
    if (pattern === '/' && path === '/') return { params: {} };
    return null;
  }

  const params: Record<string, string> = {};
  for (let i = 0; i < patternParts.length; i++) {
    const pPart = patternParts[i];
    const actual = pathParts[i];
    if (pPart.startsWith(':')) {
      const paramName = pPart.slice(1);
      params[paramName] = decodeURIComponent(actual);
    } else if (pPart.toLowerCase() !== actual.toLowerCase()) {
      return null;
    }
  }

  return { params };
}

export function getNavigationGroups() {
  const studioItems = CANONICAL_ROUTE_MANIFEST.filter((r) => r.group === 'studio' && r.navigationVisible !== false).map(
    (r) => ({
      id: r.id,
      label: r.label,
      iconName: r.iconName || 'Folder',
      badge: r.badge,
    })
  );

  const systemItems = CANONICAL_ROUTE_MANIFEST.filter((r) => r.group === 'system' && r.navigationVisible !== false).map(
    (r) => ({
      id: r.id,
      label: r.label,
      iconName: r.iconName || 'Server',
      badge: r.badge,
    })
  );

  return [
    { id: 'studio', title: 'STUDIO', items: studioItems },
    { id: 'system', title: 'SYSTEM', items: systemItems },
  ];
}
