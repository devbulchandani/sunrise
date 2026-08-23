import { useCallback, useEffect, useRef, useState } from "react";

interface PollState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
}

/**
 * Polls an async fetcher on an interval and exposes a manual refresh.
 * The fetcher is kept in a ref so callers can pass inline closures.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 30_000) {
  const [state, setState] = useState<PollState<T>>({
    data: null,
    error: null,
    loading: true,
  });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    try {
      const data = await fetcherRef.current();
      setState({ data, error: null, loading: false });
    } catch (err) {
      setState((prev) => ({
        data: prev.data,
        error: err instanceof Error ? err : new Error(String(err)),
        loading: false,
      }));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { ...state, refresh };
}

/**
 * A ticking clock for relative timestamps. Re-renders the consumer
 * every `intervalMs` so "2m ago" labels stay honest.
 */
export function useNow(intervalMs = 1_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
