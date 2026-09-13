import { ApiOutlined, CheckCircleFilled, CloseCircleFilled, LoadingOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import { useCallback, useEffect, useState } from "react";
import { request } from "../../api/httpClient.js";

// API 同步：一鍵檢查是否連上後端即時資料源（透過 Vite proxy 打 /data/status）。
// 顯示連線狀態燈，點擊重新檢查。掛在外觀切換（日光/夜間）旁。
// 註：瀏覽器無法在使用者主機執行終端機指令（cp/npm 等安全限制），
//     一鍵啟動請用專案根的 start.sh；此鍵負責「驗證/顯示」與後端的連線同步狀態。
export default function ApiSyncButton() {
  const [state, setState] = useState("idle"); // idle | checking | ok | fail
  const [detail, setDetail] = useState("");

  const check = useCallback(async () => {
    setState("checking");
    setDetail("正在同步後端即時資料源…");
    try {
      const s = await request("/data/status", { timeoutMs: 25000 });
      const live = s?.freshness_counts?.live ?? 0;
      const stale = s?.freshness_counts?.stale ?? 0;
      const known = live + stale + (s?.freshness_counts?.historical ?? 0) + (s?.freshness_counts?.mock ?? 0);
      // 後端回應了就先算連上；即時源還沒好只在 tooltip 說明，不要整顆燈變未連線。
      if (s?.primary_available) {
        setState("ok");
        setDetail(`已連上後端（${s.mode}）｜即時站點 ${live} 站`);
      } else if (known > 0) {
        setState("ok");
        setDetail(`已連上後端（${s.mode}）｜目前 ${known} 站（非即時或降級）`);
      } else {
        setState("fail");
        setDetail(`後端可達但資料源未就緒（${s?.mode ?? "未知"}）`);
      }
    } catch (err) {
      setState("fail");
      setDetail(err?.message || "連不到後端，請確認雲端後端位址或改用本機後端");
    }
  }, []);

  // 進站自動同步一次，讓使用者一眼看到是否已連上雲端即時資料。
  useEffect(() => {
    check();
  }, [check]);

  const meta = {
    idle: { icon: <ApiOutlined />, color: undefined, label: "API 同步" },
    checking: { icon: <LoadingOutlined />, color: undefined, label: "同步中" },
    ok: { icon: <CheckCircleFilled style={{ color: "#3fae5a" }} />, color: undefined, label: "已連線" },
    fail: { icon: <CloseCircleFilled style={{ color: "#e5484d" }} />, color: "danger", label: "未連線" },
  }[state];

  return (
    <Tooltip title={detail || "點擊檢查與後端的連線同步狀態"}>
      <Button
        size="small"
        icon={meta.icon}
        loading={false}
        danger={state === "fail"}
        onClick={check}
        aria-label="API 同步：檢查後端連線"
      >
        {meta.label}
      </Button>
    </Tooltip>
  );
}
