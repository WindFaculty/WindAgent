/**
 * Shared App Root Component (P4.1 & P4.6).
 * Unified shell across Desktop and Web platforms.
 */

import React, { useEffect, Suspense } from 'react';
import {
  AppShell,
  TopBar,
  Sidebar,
  MainWorkspace,
  BackendStatus,
  NavigationGroup,
} from '@windagent/studio-shell';
import { AppProviders } from './providers';
import { useRouter, RouterOutlet } from './router';
import { getNavigationGroups, type RouteDescriptor } from './routeManifest';
import { useUIStore } from '../state/uiStore';
import type { PlatformAdapter } from '../platform/platformAdapter';
import { useApiClient } from '../api/ApiProvider';
import { DashboardPage } from '../features/dashboard/pages/DashboardPage';
import { MonitoringPage } from '../features/monitoring/pages/MonitoringPage';
import { ProjectsPage } from '../features/projects/pages/ProjectsPage';
import { ProjectDetailPage } from '../features/projects/pages/ProjectDetailPage';
import { StudioHomePage } from '../features/studio/pages/StudioHomePage';
import { EpisodesPage } from '../features/episodes/pages/EpisodesPage';
import { EpisodeWorkspacePage } from '../features/episodes/pages/EpisodeWorkspacePage';




import { CharactersPage } from '../features/characters/pages/CharactersPage';
import { WorldPage } from '../features/world/pages/WorldPage';
import { StoryboardPage } from '../features/storyboard/pages/StoryboardPage';
import { ReviewsPage } from '../features/reviews/pages/ReviewsPage';
import { AssetsPage } from '../features/assets/pages/AssetsPage';
import { ProductionPage } from '../features/production/pages/ProductionPage';
import { AgentWorkspacePage } from '../features/agent-workspace/pages/AgentWorkspacePage';
import { AgentsPage } from '../features/agents/pages/AgentsPage';
import { WorkflowsPage } from '../features/workflows/pages/WorkflowsPage';
import { ModelsPage } from '../features/models/pages/ModelsPage';
import { ProvidersPage } from '../features/providers/pages/ProvidersPage';
import { RoutingPage } from '../features/routing/pages/RoutingPage';

export const PageSkeleton: React.FC<{ tabId?: string }> = ({ tabId }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      minHeight: '400px',
      color: 'var(--text-muted, #c2c6d6)',
      gap: '16px',
      fontFamily: 'var(--font-sans, sans-serif)',
    }}
  >
    <div
      style={{
        width: '32px',
        height: '32px',
        border: '3px solid var(--bg-panel-light, #171f33)',
        borderTop: '3px solid var(--color-primary, #4d8eff)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }}
    />
    <span style={{ fontSize: '14px', letterSpacing: '0.5px', opacity: 0.8 }}>
      {tabId ? `Loading ${tabId}...` : 'Loading page...'}
    </span>
  </div>
);

export interface SharedAppContentProps {
  customRouteRenderer?: (route: RouteDescriptor, params: Record<string, string>) => React.ReactNode;
}

const SharedAppContent: React.FC<SharedAppContentProps> = ({ customRouteRenderer }) => {
  const { currentRoute, activeTab, navigate } = useRouter();
  const navigationGroups = getNavigationGroups();

  const {
    backendOnline,
    setBackendOnline,
    hermesOnline,
    setHermesOnline,
  } = useUIStore();

  // Health check query via typed API client
  const apiClient = useApiClient();
  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const res = await apiClient.system.getHealth();
        if (mounted) {
          setBackendOnline(res.status === 'healthy' || res.status === 'ok');
          setHermesOnline(true);
        }
      } catch {
        if (mounted) {
          setBackendOnline(false);
          setHermesOnline(false);
        }
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [apiClient, setBackendOnline, setHermesOnline]);

  const handleSelectTab = (tabId: string) => {
    navigate(tabId);
  };

  const defaultRouteRenderer = (route: RouteDescriptor, params: Record<string, string>) => {
    if (customRouteRenderer) {
      const rendered = customRouteRenderer(route, params);
      if (rendered) return rendered;
    }

    if (route.id === 'dashboard') {
      return <DashboardPage />;
    }

    if (route.id === 'monitoring') {
      return <MonitoringPage />;
    }

    if (route.id === 'studio') {
      return <StudioHomePage />;
    }

    if (route.id === 'projects') {
      return <ProjectsPage />;
    }

    if (route.id === 'project-detail') {
      return <ProjectDetailPage projectId={params.projectId} />;
    }

    if (route.id === 'episodes') {
      return <EpisodesPage />;
    }

    if (route.id === 'episode-workspace') {
      return <EpisodeWorkspacePage episodeId={params.episodeId} />;
    }

    if (route.id === 'characters') {
      return <CharactersPage projectId={params.projectId ?? 'proj-cyberpunk-01'} />;
    }

    if (route.id === 'world') {
      return <WorldPage projectId={params.projectId ?? 'proj-cyberpunk-01'} />;
    }

    if (route.id === 'storyboard') {
      return <StoryboardPage episodeId={params.episodeId ?? 'ep-cb-001'} />;
    }

    if (route.id === 'reviews') {
      return <ReviewsPage episodeId={params.episodeId} projectId={params.projectId} />;
    }

    if (route.id === 'assets') {
      return <AssetsPage episodeId={params.episodeId} projectId={params.projectId} />;
    }

    if (route.id === 'episode-production') {
      return <ProductionPage episodeId={params.episodeId ?? 'ep-cb-001'} />;
    }

    if (route.id === 'production-script') {
      return <ProductionPage episodeId={params.episodeId ?? 'ep-cb-001'} initialTab="shots" />;
    }

    if (route.id === 'production-assets') {
      return <ProductionPage episodeId={params.episodeId ?? 'ep-cb-001'} initialTab="audio" />;
    }

    if (route.id === 'production-video') {
      return <ProductionPage episodeId={params.episodeId ?? 'ep-cb-001'} initialTab="render" />;
    }

    if (route.id === 'workspace') {
      return <AgentWorkspacePage conversationId={params.conversationId} />;
    }

    if (route.id === 'agents') {
      return <AgentsPage />;
    }

    if (route.id === 'workflows') {
      return <WorkflowsPage />;
    }

    if (route.id === 'models-library' || route.id === 'models') {
      return <ModelsPage />;
    }

    if (route.id === 'models-endpoints' || route.id === 'providers') {
      return <ProvidersPage />;
    }

    if (route.id === 'router' || route.id === 'routing') {
      return <RoutingPage />;
    }

    return (
      <div style={{ padding: '32px', color: 'var(--studio-text, #f1f5f9)' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 600, margin: '0 0 8px 0' }}>{route.label}</h2>
        <p style={{ color: '#94a3b8', fontSize: '14px' }}>
          Path: <code>{route.path}</code> | Group: <code>{route.group}</code>
        </p>
      </div>
    );
  };


  return (
    <AppShell
      header={
        <TopBar
          statusSlot={<BackendStatus backendOnline={backendOnline} hermesOnline={hermesOnline} />}
        />
      }
    >
      <MainWorkspace
        sidebar={
          <Sidebar>
            {navigationGroups.map((group) => (
              <NavigationGroup
                key={group.id}
                group={group}
                activeTab={activeTab}
                onSelectTab={handleSelectTab}
              />
            ))}
          </Sidebar>
        }
      >
        <Suspense fallback={<PageSkeleton tabId={currentRoute.id} />}>
          <RouterOutlet renderRoute={defaultRouteRenderer} />
        </Suspense>
      </MainWorkspace>
    </AppShell>
  );
};

export interface AppProps {
  platform?: PlatformAdapter;
  customRouteRenderer?: (route: RouteDescriptor, params: Record<string, string>) => React.ReactNode;
}

export const App: React.FC<AppProps> = ({ platform, customRouteRenderer }) => {
  return (
    <AppProviders platform={platform}>
      <SharedAppContent customRouteRenderer={customRouteRenderer} />
    </AppProviders>
  );
};
