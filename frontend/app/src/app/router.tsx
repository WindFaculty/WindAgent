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
  const normalizePath = useCallback((raw: string): string => {
    if (!raw) return '/dashboard';
    const qIdx = raw.indexOf('?');
    let pathPart = qIdx === -1 ? raw : raw.slice(0, qIdx);
    const queryPart = qIdx === -1 ? '' : raw.slice(qIdx);
    pathPart = pathPart.replace(/\/+/g, '/');
    if (!pathPart.startsWith('/')) pathPart = `/${pathPart}`;
    if (pathPart.length > 1 && pathPart.endsWith('/')) pathPart = pathPart.slice(0, -1);
    const normalized = `${pathPart}${queryPart}`;
    return normalized || '/dashboard';
  }, []);

  const getHashPath = useCallback((): string => {
    if (typeof window === 'undefined') return normalizePath(initialPath || '/dashboard');
    const hash = window.location.hash.replace(/^#/, '').trim();
    if (!hash || hash === '/') return normalizePath(initialPath || '/dashboard');
    return normalizePath(hash);
  }, [initialPath, normalizePath]);

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
    let destPath = target.trim();
    if (!destPath) destPath = '/dashboard';
    // If target doesn't look like a path (no slash) try id lookup first; otherwise treat as path
    if (!destPath.startsWith('/')) {
      const byId = findRouteById(destPath);
      if (byId) destPath = byId.path;
      else destPath = `/${destPath}`;
    }

    if (params) {
      for (const [k, v] of Object.entries(params)) {
        // Replace :param occurrences; encode value but preserve slashes inside param by encoding
        destPath = destPath.replace(`:${k}`, encodeURIComponent(v));
      }
      // If any :param remains unreplaced, leave as-is (will 404) — do not silently drop
    }

    destPath = normalizePath(destPath);

    if (typeof window !== 'undefined') {
      // Avoid pushing duplicate history entry if already at dest
      const currentHash = window.location.hash.replace(/^#/, '');
      const normalizedCurrent = normalizePath(currentHash || '/');
      if (normalizedCurrent !== destPath) {
        window.location.hash = `#${destPath}`;
      }
    }
    setCurrentPath(destPath);
  }, [normalizePath]);

  const goBack = useCallback(() => {
    if (typeof window === 'undefined') return;
    // If no prior hash history, navigate to dashboard instead of leaving the app
    if (window.history.length <= 1) {
      window.location.hash = '#/dashboard';
      setCurrentPath('/dashboard');
      return;
    }
    window.history.back();
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
