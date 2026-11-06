import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { useStore } from '../session/store';
import { ApiError } from './client';

/* Load something from the API for a screen. It reloads when the screen comes back into focus, when the
   signed-in side changes, and whenever any change anywhere calls refresh(). `data` keeps the last result
   while a reload runs, so screens don't flash. */
export function useQuery<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const { version, s } = useStore();
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | null>(null);
  const seq = useRef(0);
  const loadRef = useRef(load);
  useLayoutEffect(() => { loadRef.current = load; });
  const run = useCallback(async () => {
    const n = ++seq.current;
    try {
      const d = await loadRef.current();
      if (n === seq.current) { setData(d); setError(null); }
    } catch (e) {
      if (n === seq.current) setError(e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e)));
    }
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run(); }, [run, version, s.role, s.session?.token, ...deps]);
  useFocusEffect(useCallback(() => { if (seq.current) run(); }, [run]));
  return { data, error, reload: run, setData };
}

/* Run a change, show the server's message if it fails, and refresh every screen if it works. */
export function useAction() {
  const { refresh, toast } = useStore();
  const [busy, setBusy] = useState(false);
  const act = useCallback(async <T,>(fn: () => Promise<T>, done?: string | ((r: T) => string | void)): Promise<T | undefined> => {
    setBusy(true);
    try {
      const r = await fn();
      const msg = typeof done === 'function' ? done(r) : done;
      if (msg) toast(msg);
      refresh();
      return r;
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Something went wrong. Try again.');
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [refresh, toast]);
  return { act, busy };
}
