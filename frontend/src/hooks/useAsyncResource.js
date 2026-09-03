import { useCallback, useEffect, useState } from "react";

export default function useAsyncResource(loader) {
  const [state, setState] = useState({
    data: null,
    error: null,
    loading: true,
  });

  const reload = useCallback(async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      const data = await loader();
      setState({ data, error: null, loading: false });
      return data;
    } catch (error) {
      setState({ data: null, error, loading: false });
      throw error;
    }
  }, [loader]);

  useEffect(() => {
    reload().catch(() => {
      // 錯誤已保留在 state，交由頁面明確呈現。
    });
  }, [reload]);

  return { ...state, reload };
}
