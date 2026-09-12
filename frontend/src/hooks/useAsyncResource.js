import { useCallback, useEffect, useState } from "react";

export default function useAsyncResource(loader, { getCached } = {}) {
  const [state, setState] = useState(() => {
    const cached = getCached?.() ?? null;
    return { data: cached, error: null, loading: cached == null };
  });

  const reload = useCallback(async ({ silent = false } = {}) => {
    setState((current) => ({
      ...current,
      error: null,
      loading: silent || current.data ? false : true,
    }));
    try {
      const data = await loader();
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
  }, [loader]);

  useEffect(() => {
    const hasCache = getCached?.() != null;
    reload({ silent: hasCache }).catch(() => {
      // 錯誤已保留在 state，交由頁面明確呈現。
    });
  }, [reload]);

  return { ...state, reload };
}
