/**
 * Canonical Router Engine (P4.4 & P4.6).
 * Hash-based routing without TabKeeper/activeTab authority.
 */

import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import { findRouteByPath, findRouteById, type RouteDescriptor } from './routeManifest';
import { RouteErrorBoundary } from './errors/RouteErrorBoundary';

export interface RouterState {
  currentPath: string;
  currentRoute: RouteDescriptor;
  params: Record<string, string>;
  activeTab: string;
  navigate: (target: string, params?: Record<string, string>) => void;
  goBack: () => void;
  goForward: () => void;
}

const defaultRoute: RouteDescriptor = {
  id: 'dashboard',
  path: '/dashboard',
  label: 'Dashboard',
  group: 'studio',
};

const RouterContext = createContext<RouterState>({
  currentPath: '/dashboard',
  currentRoute: defaultRoute,
  params: {},
  activeTab: 'dashboard',
  navigate: () => {},
  goBack: () => {},
  goForward: () => {},
});

export interface RouterProviderProps {
  initialPath?: string;
  children: React.ReactNode;
}

export const RouterProvider: React.FC<RouterProviderProps> = ({ initialPath, children }) => {
  const getHashPath = useCallback((): string => {
    if (typeof window === 'undefined') return initialPath || '/dashboard';
    const hash = window.location.hash.replace(/^#/, '').trim();
    return hash.startsWith('/') ? hash : `/${hash}`;
  }, [initialPath]);

  const [currentPath, setCurrentPath] = useState<string>(() => getHashPath() || '/dashboard');

  const resolved = useMemo(() => {
    const matched = findRouteByPath(currentPath);
    if (matched) {
      return { route: matched.route, params: matched.params };
    }
    // Fallback 404 route
    const notFoundRoute: RouteDescriptor = {
      id: 'not-found',
      path: currentPath,
      label: 'Not Found',
      group: 'studio',
    };
    return { route: notFoundRoute, params: {} };
  }, [currentPath]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleHashChange = () => {
      const nextPath = getHashPath();
      setCurrentPath(nextPath);
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [getHashPath]);

  const navigate = useCallback((target: string, params?: Record<string, string>) => {
    let destPath = target;
    if (!target.startsWith('/')) {
      const byId = findRouteById(target);
      destPath = byId ? byId.path : `/${target}`;
    }

    if (params) {
      for (const [k, v] of Object.entries(params)) {
        destPath = destPath.replace(`:${k}`, encodeURIComponent(v));
      }
    }

    if (typeof window !== 'undefined') {
      window.location.hash = `#${destPath}`;
    }
    setCurrentPath(destPath);
  }, []);

  const goBack = useCallback(() => {
    if (typeof window !== 'undefined') window.history.back();
  }, []);

  const goForward = useCallback(() => {
    if (typeof window !== 'undefined') window.history.forward();
  }, []);

  const contextValue: RouterState = {
    currentPath,
    currentRoute: resolved.route,
    params: resolved.params,
    activeTab: resolved.route.id,
    navigate,
    goBack,
    goForward,
  };

  return <RouterContext.Provider value={contextValue}>{children}</RouterContext.Provider>;
};

export function useRouter(): RouterState {
  return useContext(RouterContext);
}

export function useNavigate() {
  const { navigate } = useRouter();
  return navigate;
}

export interface RouterOutletProps {
  renderRoute: (route: RouteDescriptor, params: Record<string, string>) => React.ReactNode;
}

export const RouterOutlet: React.FC<RouterOutletProps> = ({ renderRoute }) => {
  const { currentRoute, params, currentPath } = useRouter();

  if (currentRoute.id === 'not-found') {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: '400px',
          color: 'var(--studio-text, #f1f5f9)',
          padding: '32px',
          textAlign: 'center',
        }}
      >
        <h3 style={{ fontSize: '24px', fontWeight: 600, color: '#f87171', margin: '0 0 8px 0' }}>404 — Page Not Found</h3>
        <p style={{ color: '#94a3b8', fontSize: '14px', margin: '0 0 20px 0' }}>
          No view mapped to path <code>{currentPath}</code>
        </p>
        <button
          onClick={() => (window.location.hash = '#/dashboard')}
          style={{
            backgroundColor: 'var(--color-primary, #3b82f6)',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            padding: '8px 16px',
            fontSize: '13px',
            cursor: 'pointer',
          }}
        >
          Go to Dashboard
        </button>
      </div>
    );
  }

  return (
    <RouteErrorBoundary routePath={currentPath}>
      {renderRoute(currentRoute, params)}
    </RouteErrorBoundary>
  );
};
