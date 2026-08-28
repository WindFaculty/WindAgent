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
      { id: 'world', label: 'World', iconName: 'Globe' },
      { id: 'assets', label: 'Assets', iconName: 'Package' },
      { id: 'reviews', label: 'Reviews', iconName: 'CheckSquare' },
      { id: 'live-record', label: 'Live Record', iconName: 'Video' },
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
        iconName: 'Clapperboard',
        badge: 'PREVIEW',
        children: [
          { id: 'production-script', label: 'Script', iconName: 'FileText' },
          { id: 'production-assets', label: 'Assets', iconName: 'Package' },
          { id: 'production-video', label: 'Video', iconName: 'Film' },
        ],
      },
    ],
  },

  {
    id: 'system',
    title: 'SYSTEM',
    items: [
      { id: 'workspace', label: 'Agent Workspace', iconName: 'Bot' },
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
