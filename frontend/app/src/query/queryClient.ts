/**
 * QueryClient — Lightweight reactive query cache and state management engine (P4.8).
 */

export type QueryKey = readonly unknown[];

export interface QueryState<TData = unknown, TError = Error> {
  data: TData | undefined;
  error: TError | null;
  isLoading: boolean;
  isFetching: boolean;
  isSuccess: boolean;
  isError: boolean;
  updatedAt: number;
}

export interface QueryObserverOptions<TData = unknown> {
  queryKey: QueryKey;
  queryFn: () => Promise<TData>;
  staleTimeMs?: number;
  enabled?: boolean;
}

export type QueryListener<TData = any> = (state: QueryState<TData>) => void;

export class QueryClient {
  private cache = new Map<string, { state: QueryState<any>; promise?: Promise<any> }>();
  private listeners = new Map<string, Set<QueryListener>>();

  private hashKey(key: QueryKey): string {
    return JSON.stringify(key);
  }

  getQueryState<TData = unknown>(key: QueryKey): QueryState<TData> | undefined {
    return this.cache.get(this.hashKey(key))?.state;
  }

  setQueryData<TData = unknown>(key: QueryKey, data: TData): void {
    const hash = this.hashKey(key);
    const existing = this.cache.get(hash);
    const nextState: QueryState<TData> = {
      data,
      error: null,
      isLoading: false,
      isFetching: false,
      isSuccess: true,
      isError: false,
      updatedAt: Date.now(),
    };
    this.cache.set(hash, { ...existing, state: nextState });
    this.notify(hash, nextState);
  }

  async fetchQuery<TData = unknown>(options: QueryObserverOptions<TData>): Promise<TData> {
    const hash = this.hashKey(options.queryKey);
    const existing = this.cache.get(hash);

    const now = Date.now();
    const staleTime = options.staleTimeMs ?? 5000;
    if (existing?.state.data !== undefined && now - existing.state.updatedAt < staleTime) {
      return existing.state.data as TData;
    }

    if (existing?.promise) {
      return existing.promise;
    }

    const currentState = existing?.state ?? {
      data: undefined,
      error: null,
      isLoading: true,
      isFetching: true,
      isSuccess: false,
      isError: false,
      updatedAt: 0,
    };

    const nextState: QueryState<TData> = {
      ...currentState,
      isLoading: currentState.data === undefined,
      isFetching: true,
    };
    this.cache.set(hash, { state: nextState });
    this.notify(hash, nextState);

    const promise = options
      .queryFn()
      .then((data) => {
        const successState: QueryState<TData> = {
          data,
          error: null,
          isLoading: false,
          isFetching: false,
          isSuccess: true,
          isError: false,
          updatedAt: Date.now(),
        };
        this.cache.set(hash, { state: successState });
        this.notify(hash, successState);
        return data;
      })
      .catch((error: Error) => {
        const errorState: QueryState<TData> = {
          data: existing?.state.data,
          error,
          isLoading: false,
          isFetching: false,
          isSuccess: false,
          isError: true,
          updatedAt: Date.now(),
        };
        this.cache.set(hash, { state: errorState });
        this.notify(hash, errorState);
        throw error;
      })
      .finally(() => {
        const current = this.cache.get(hash);
        if (current) {
          current.promise = undefined;
        }
      });

    const curr = this.cache.get(hash);
    if (curr) curr.promise = promise;
    return promise;
  }

  invalidateQueries(filters?: { queryKey?: QueryKey }): void {
    if (!filters || !filters.queryKey) {
      for (const entry of this.cache.values()) {
        entry.state.updatedAt = 0;
      }
      return;
    }

    const prefix = JSON.stringify(filters.queryKey).slice(0, -1);
    for (const [hash, entry] of this.cache.entries()) {
      if (hash.startsWith(prefix)) {
        entry.state.updatedAt = 0;
      }
    }
  }

  subscribe(key: QueryKey, listener: QueryListener): () => void {
    const hash = this.hashKey(key);
    let set = this.listeners.get(hash);
    if (!set) {
      set = new Set();
      this.listeners.set(hash, set);
    }
    set.add(listener);
    return () => {
      set?.delete(listener);
    };
  }

  private notify(hash: string, state: QueryState<any>) {
    const set = this.listeners.get(hash);
    if (set) {
      for (const listener of set) {
        try {
          listener(state);
        } catch {
          // ignore error
        }
      }
    }
  }
}

export function createQueryClient(): QueryClient {
  return new QueryClient();
}
