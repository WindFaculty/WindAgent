/**
 * useSearchParams — Hash-compatible search param hook for the canonical
 * hash router (P4.6). Mirrors the react-router-dom v6 API surface used by
 * feature pages (get + set) without introducing a second routing engine.
 */

import { useCallback, useEffect, useState } from 'react';

function parseHashSearch(): URLSearchParams {
  if (typeof window === 'undefined') return new URLSearchParams();
  const hash = window.location.hash || '';
  const qIndex = hash.indexOf('?');
  return new URLSearchParams(qIndex >= 0 ? hash.slice(qIndex + 1) : '');
}

type SearchParamsInit = Record<string, string | number | boolean | null | undefined> | URLSearchParams | string;

function toURLSearchParams(init: SearchParamsInit): URLSearchParams {
  if (init instanceof URLSearchParams) return new URLSearchParams(init);
  if (typeof init === 'string') return new URLSearchParams(init);
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(init)) {
    if (value === null || value === undefined) continue;
    params.set(key, String(value));
  }
  return params;
}

export function useSearchParams(): [URLSearchParams, (init: SearchParamsInit, options?: { replace?: boolean }) => void] {
  const [params, setParams] = useState<URLSearchParams>(() => parseHashSearch());

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onHashChange = () => setParams(parseHashSearch());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const setSearchParams = useCallback((init: SearchParamsInit, options?: { replace?: boolean }) => {
    if (typeof window === 'undefined') return;
    const nextParams = toURLSearchParams(init);
    const hash = window.location.hash || '#/';
    const path = hash.split('?')[0];
    const queryString = nextParams.toString();
    const nextHash = queryString ? `${path}?${queryString}` : path;

    if (options?.replace) {
      const url = `${window.location.pathname}${window.location.search}#${nextHash.replace(/^#/, '')}`;
      window.location.replace(url);
    } else {
      window.location.hash = nextHash;
    }
    setParams(nextParams);
  }, []);

  return [params, setSearchParams];
}
