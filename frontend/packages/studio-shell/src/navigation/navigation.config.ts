import { NavigationGroupDescriptor } from './navigation.types';

export const DESKTOP_NAVIGATION_GROUPS: NavigationGroupDescriptor[] = [
  {
    id: 'studio',
    title: 'STUDIO',
    items: [
      { id: 'dashboard', label: 'Dashboard', iconName: 'LayoutDashboard' },
      { id: 'studio', label: 'Studio', iconName: 'Clapperboard' },
      { id: 'projects', label: 'Projects', iconName: 'Folder' },
      { id: 'episodes', label: 'Episodes', iconName: 'Film' },
      { id: 'storyboard', label: 'Story Board', iconName: 'LayoutGrid' },
      { id: 'characters', label: 'Characters', iconName: 'Users' },
      { id: 'world', label: 'World / Setting', iconName: 'Globe' },
      { id: 'assets', label: 'Assets', iconName: 'Package' },
      { id: 'reviews', label: 'Reviews', iconName: 'CheckSquare' },
    ],
  },
  {
    id: 'production',
    title: 'PRODUCTION',
    badge: 'ROADMAP 2',
    defaultCollapsed: true,
    items: [
      {
        id: 'production',
        label: 'Production',
        iconName: 'Film',
        badge: 'PREVIEW',
        children: [
          { id: 'production-script', label: 'Script Workspace', iconName: 'FileText', badge: 'PREVIEW' },
          { id: 'production-assets', label: 'Asset Library', iconName: 'Palette', badge: 'PREVIEW' },
          { id: 'production-video', label: 'Video Workspace', iconName: 'Video', badge: 'PREVIEW' },
        ],
      },
    ],
  },
  {
    id: 'system',
    title: 'SYSTEM',
    items: [
      { id: 'workspace', label: 'Agent Workspace', iconName: 'Bot' },
      {
        id: 'models',
        label: 'Models',
        iconName: 'Cpu',
        children: [
          { id: 'models-library', label: 'Model Library' },
          { id: 'models-endpoints', label: 'Endpoints' },
        ],
      },
      { id: 'models-library', label: 'Models', iconName: 'Cpu' },
      { id: 'router', label: 'Router / Providers', iconName: 'Server' },
      { id: 'browser', label: 'Browser', iconName: 'Globe', badge: 'STUB' },
      { id: 'files', label: 'Files', iconName: 'Folder', badge: 'STUB' },
      { id: 'settings', label: 'Settings', iconName: 'Settings' },
      { id: 'agents', label: 'Agents', iconName: 'Users' },
      { id: 'workflows', label: 'Workflows', iconName: 'GitBranch', badge: 'BETA' },
      { id: 'logs', label: 'Logs', iconName: 'FileText' },
      { id: 'memory', label: 'Database', iconName: 'Database', badge: 'BETA' },
    ],
  },
];
