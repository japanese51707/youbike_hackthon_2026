import { useCallback, useEffect, useRef, useState } from "react";
import { getEscalations } from "../api/escalationApi.js";
import { isApiMode } from "../api/httpClient.js";

const POLL_MS = 30000;

/**
 * ADR-309：輪詢未結案的緊急調度案件。
 *
 * ★不在前端自己跑計時器累加等待時間——階段與分鐘數都用後端回的值。
 *   重整頁面、換一台電腦、調度員與管理後台三邊看到的數字必須一致，這是稽核前提。
 */
export default function useEscalations({ pollMs = POLL_MS } = {}) {
  const [cases, setCases] = useState([]);
  const [counts, setCounts] = useState({ open: 0, banner: 0, prompt: 0 });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(isApiMode);
  const alive = useRef(true);

  const reload = useCallback(async () => {
    if (!isApiMode) {
      setLoading(false);
      return;
    }
    try {
      const data = await getEscalations();
      if (!alive.current) return;
      setCases(data.cases ?? []);
      setCounts(data.counts ?? { open: 0, banner: 0, prompt: 0 });
      setError("");
    } catch (err) {
      // 升級提示讀不到時要講出來，不能安靜地讓畫面看起來一切正常。
      if (alive.current) setError(err.message || "無法取得警示追蹤");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    reload();
    if (!isApiMode) return () => { alive.current = false; };
    const timer = setInterval(reload, pollMs);
    return () => {
      alive.current = false;
      clearInterval(timer);
    };
  }, [pollMs, reload]);

  return {
    cases,
    counts,
    error,
    loading,
    reload,
    bannerCases: cases.filter((c) => c.should_banner),
    promptCase: cases.find((c) => c.should_prompt) ?? null,
  };
}
