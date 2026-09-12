import { useEffect, useState } from "react";
import { getActorId, isApiMode, request, setActorId } from "../api/httpClient.js";
import { pickDriverActor } from "../utils/pickDriverActor.js";

export const DRIVER_MANUAL_KEY = "youbike.driver.manual-actor";

export default function useDriverActor() {
  const [operators, setOperators] = useState([]);
  const [actorId, setActor] = useState(() => getActorId());
  const [ready, setReady] = useState(!isApiMode);

  useEffect(() => {
    if (!isApiMode) return undefined;
    let cancelled = false;
    request("/operators")
      .then((rows) => {
        if (cancelled) return;
        const list = Array.isArray(rows) ? rows : [];
        setOperators(list);
        const current = getActorId();
        const manual = globalThis.sessionStorage?.getItem(DRIVER_MANUAL_KEY);
        if (manual && manual === current) {
          setActor(current);
          setReady(true);
          return;
        }
        const currentRow = list.find((row) => row.operator_id === current);
        if (currentRow?.current_task_id) {
          setActor(current);
          setReady(true);
          return;
        }
        const next = pickDriverActor(list, current);
        if (next && next !== current) setActorId(next);
        setActor(next || current);
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const choose = (id) => {
    try {
      globalThis.sessionStorage?.setItem(DRIVER_MANUAL_KEY, id || "");
    } catch {
      /* 無痕模式寫不進去也不擋切換 */
    }
    setActorId(id);
    setActor(id);
  };

  return { operators, actorId, choose, ready };
}
