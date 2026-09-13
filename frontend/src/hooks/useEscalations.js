import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getEscalations, getMyNotifications } from "../api/escalationApi.js";
import { isApiMode } from "../api/httpClient.js";

const POLL_MS = 30000;

/**
 * ADR-335：輪詢未解除的緊急案件與「我的」分級提醒。
 *
 * ★時間一律用後端回的欄位，前端不自己跑計時器累加——重整、換電腦、
 *   調度員與管理後台三邊看到的數字必須一致，這是稽核前提。
 *
 * ★單一輪詢來源：上一輪還沒回來就不再發新請求（in-flight 擋住），
 *   卸載後忽略舊回應。失敗時保留上一次的內容並標記 stale，
 *   不要讓畫面因為一次逾時就整個空掉——未解除的案件不能消失。
 */
export default function useEscalations({ pollMs = POLL_MS } = {}) {
  const [cases, setCases] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [counts, setCounts] = useState({ open: 0, banner: 0, prompt: 0 });
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(isApiMode);
  const alive = useRef(true);
  const inFlight = useRef(false);

  const reload = useCallback(async () => {
    if (!isApiMode) {
      setLoading(false);
      return;
    }
    if (inFlight.current) return;   // 上一輪還沒回來就不疊新的
    inFlight.current = true;
    try {
      const [data, notif] = await Promise.all([
        getEscalations(),
        getMyNotifications().catch(() => ({ notifications: [] })),
      ]);
      if (!alive.current) return;
      setCases(data.cases ?? []);
      setCounts(data.counts ?? { open: 0, banner: 0, prompt: 0 });
      setNotifications(notif.notifications ?? []);
      setError("");
      setStale(false);
    } catch (err) {
      // 讀不到要講出來，但保留上一次的內容——案件沒有因為讀取失敗而解除。
      if (alive.current) {
        setError(err.message || "無法取得警示追蹤");
        setStale(true);
      }
    } finally {
      inFlight.current = false;
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

  // 依階段聚合成「N 站超過 M 分」，多站一起逾時也只呈現一行摘要
  const summary = useMemo(() => {
    const byStage = new Map();
    for (const item of cases) {
      const stage = Number(item.stage || 0);
      if (stage < 1) continue;
      const row = byStage.get(stage) || { stage, count: 0, threshold: null, worst: null };
      row.count += 1;
      const thresholds = item.stage_thresholds || [];
      row.threshold = thresholds[stage - 1] ?? row.threshold;
      if (!row.worst || (item.waited_minutes || 0) > (row.worst.waited_minutes || 0)) {
        row.worst = item;
      }
      byStage.set(stage, row);
    }
    return [...byStage.values()].sort((a, b) => b.stage - a.stage);
  }, [cases]);

  return {
    cases,
    notifications,
    counts,
    summary,
    error,
    stale,
    loading,
    reload,
    bannerCases: cases.filter((c) => c.should_banner),
    // ADR-335：不再有「該強制彈窗」的語意。最嚴重的案件只用來當摘要標題，
    // 詳情一律由使用者主動點開。
    worstCase: cases.find((c) => c.stage >= 2) ?? cases[0] ?? null,
  };
}
