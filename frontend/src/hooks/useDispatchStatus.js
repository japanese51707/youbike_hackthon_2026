import { useCallback, useEffect, useRef, useState } from "react";
import { getOperationsOverview } from "../api/operationsApi.js";

// 分派任務狀況資料源：定期輪詢 GET /dispatch/overview（一次拿 tasks + operators + vehicles）。
// 站點完成/任務結案由後端 ADR-310 自動偵測推進，這裡只負責定期取最新狀態呈現。
export default function useDispatchStatus(pollMs = 15000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const overview = await getOperationsOverview();
      setData(overview);
      setError(null);
    } catch (err) {
      setError(err?.message || "取得分派任務狀況失敗");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    timer.current = setInterval(() => load({ silent: true }), pollMs);
    return () => clearInterval(timer.current);
  }, [load, pollMs]);

  return { data, error, loading, reload: () => load({ silent: true }) };
}
