import { useCallback, useEffect, useState } from "react";
import { peekResource, rememberResource } from "../api/resourceCache.js";

export default function useAsyncResource(loader, { getCached, cacheKey, enabled = true } = {}) {
  const readCached = () => {
    const fromHook = getCached?.();
    if (fromHook != null) return fromHook;
    return cacheKey ? peekResource(cacheKey) : null;
  };

  const [state, setState] = useState(() => {
    const cached = readCached();
    return { data: cached, error: null, loading: cached == null && enabled };
  });

  const reload = useCallback(async ({ silent = false } = {}) => {
    setState((current) => ({
      ...current,
      error: null,
      loading: current.data || silent ? false : true,
    }));
    try {
      const data = await loader();
      if (data == null) {
        setState((current) => ({
          data: current.data,
          error: null,
          loading: false,
        }));
        return data;
      }
      if (cacheKey) rememberResource(cacheKey, data);
      setState({ data, error: null, loading: false });
      return data;
    } catch (error) {
      setState((current) => ({
        data: current.data,
        error,
        loading: false,
      }));
      throw error;
    }
  }, [loader, cacheKey]);

  useEffect(() => {
    if (!enabled) return undefined;
    const hasCache = readCached() != null;
    reload({ silent: hasCache }).catch(() => {
      // 錯誤已保留在 state，交由頁面明確呈現。
    });
    return undefined;
  }, [reload, enabled]);

  return { ...state, reload };
}
