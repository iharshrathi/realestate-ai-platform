import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Run an async function and track { data, loading, error }.
 * Re-runs when `deps` change; call `reload()` to refresh manually.
 * Stale responses (from an older request) are ignored.
 */
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const latest = useRef(0);

  const run = useCallback(() => {
    const id = ++latest.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => id === latest.current && setState({ data, loading: false, error: null }))
      .catch((error) => id === latest.current && setState({ data: null, loading: false, error }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(run, [run]);
  return { ...state, reload: run };
}
