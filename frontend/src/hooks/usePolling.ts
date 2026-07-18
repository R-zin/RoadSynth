import { useEffect, useRef, useState } from 'react';

interface PollingState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Fetches `fetcher` immediately and then every `intervalMs` while `enabled`.
 * The fetcher is kept in a ref so the effect does not restart on every render.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  enabled = true,
): PollingState<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [state, setState] = useState<PollingState<T>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    if (!enabled) return;
    let active = true;

    const run = async () => {
      try {
        const d = await fetcherRef.current();
        if (active) setState({ data: d, error: null, loading: false });
      } catch (e) {
        if (active)
          setState((s) => ({
            ...s,
            error: e instanceof Error ? e.message : 'Request failed',
            loading: false,
          }));
      }
    };

    run();
    const id = setInterval(run, intervalMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [intervalMs, enabled]);

  return state;
}
