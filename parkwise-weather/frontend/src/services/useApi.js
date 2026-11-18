import { useCallback, useEffect, useState } from "react";

/**
 * Runs an API call when `deps` change and tracks loading / error / data.
 * Aborts the in-flight request if the component unmounts or deps change,
 * so a slow old response can never overwrite a newer one.
 *
 *   const { data, loading, error, reload } = useApi((signal) => api.listParks(null, { signal }), []);
 *
 * Pass `enabled = false` to skip the call (e.g. until a park is selected).
 */
export function useApi(fetcher, deps, enabled = true) {
  const [state, setState] = useState({ data: null, loading: enabled, error: null });
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, loading: false, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setState((prev) => ({ ...prev, loading: true, error: null }));
    fetcher(controller.signal)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error) => {
        if (error.name !== "AbortError") setState({ data: null, loading: false, error });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, attempt]);

  return { ...state, reload };
}
