"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiGet, queryString, type Params } from "./client";
import { scopeParams, type Scope } from "./filters";

export type ApiState<T> = {
  /** The last good answer for the current key. Null while loading, and after an error. */
  data: T | null;
  error: ApiError | null;
  /** True from the start of a fetch until it ends. */
  loading: boolean;
  /** Fetch again. Stale data stays on screen until the new answer arrives. */
  reload: () => void;
};

type Result<T> = {
  key: string;
  tick: number;
  data: T | null;
  error: ApiError | null;
};

/**
 * One fetch for each `key`. A new key aborts the old request, and an answer for
 * an old key is never shown. `fetcher` may read the clock (the time window).
 */
export function useQuery<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
  enabled = true,
): ApiState<T> {
  const [result, setResult] = useState<Result<T>>({
    key: "",
    tick: 0,
    data: null,
    error: null,
  });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    fetcher(controller.signal).then(
      (data) => setResult({ key, tick, data, error: null }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({
          key,
          tick,
          data: null,
          error:
            error instanceof ApiError
              ? error
              : new ApiError(0, "client_error", String(error)),
        });
      },
    );
    return () => controller.abort();
    // `fetcher` is rebuilt on every render. `key` stands for what it fetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  // An answer for another key is never shown. After a reload the old answer
  // of the same key stays until the new one arrives.
  const current = enabled && result.key === key;
  return {
    data: current ? result.data : null,
    error: current ? result.error : null,
    loading: enabled && !(current && result.tick === tick),
    reload,
  };
}

/** GET /api/<path> with fixed parameters. */
export function useApi<T>(
  path: string,
  params: Params = {},
  { enabled = true }: { enabled?: boolean } = {},
): ApiState<T> {
  const key = `${path}${queryString(params)}`;
  return useQuery<T>(key, (signal) => apiGet<T>(path, params, signal), enabled);
}

/**
 * GET /api/<path> with the global filters (site, range, class) and `extra`
 * parameters. `from` and `to` are computed when the request starts.
 */
export function useScopedApi<T>(
  path: string,
  scope: Scope,
  extra: Params = {},
  { enabled = true }: { enabled?: boolean } = {},
): ApiState<T> {
  const key = `${path}|${scope.site}|${scope.range}|${scope.classes}${queryString(extra)}`;
  return useQuery<T>(
    key,
    (signal) => apiGet<T>(path, { ...scopeParams(scope), ...extra }, signal),
    enabled,
  );
}
