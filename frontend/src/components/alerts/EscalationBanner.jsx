import { AlertOutlined, DownOutlined, RightOutlined, UpOutlined } from "@ant-design/icons";
import { Button, Tag } from "antd";
import { useState } from "react";
import { formatWaited } from "../../api/escalationApi.js";

/**
 * ADR-335：跨頁常駐的「可收合彙總橫幅」。
 *
 * 取代 ADR-309 的強制彈窗。舊版 45 分鐘會跳出 closable={false} 的 modal 擋住整頁，
 * 早尖峰多站同時逾時就等於把調度員鎖在原地——他連去派工都做不到。
 *
 * 這裡的規則：
 *   - 全域最多一條橫幅，逾時多站聚合成「3 站超過 60 分、8 站超過 45 分」。
 *   - 可以收合成一行，但不會消失——案件只有「確認解除」才會不見。
 *   - 詳情由使用者自己點開，隨時可關；關閉不需要先呼叫成功任何 API。
 */
export default function EscalationBanner({ summary, cases, onOpen, hint = "", stale = false }) {
  const [collapsed, setCollapsed] = useState(false);
  if (!summary?.length) return null;

  const top = summary[0];
  const worst = top.worst;
  const critical = top.stage >= 3;

  return (
    <div
      className={`escalation-banner${critical ? " is-critical" : ""}${collapsed ? " is-collapsed" : ""}`}
      role="status"
    >
      <AlertOutlined className="escalation-banner-icon" />

      <div className="escalation-banner-text">
        <strong>
          {summary
            .map((row) => `${row.count} 站超過 ${row.threshold ?? "—"} 分`)
            .join("、")}
        </strong>
        {!collapsed && worst ? (
          <span className="escalation-banner-sub">
            最久：{worst.station_name}（{worst.district}）｜{worst.trigger_reason}
          </span>
        ) : null}
      </div>

      {!collapsed && worst ? (
        <Tag color={critical ? "red" : "orange"} className="escalation-banner-tag">
          已持續 {formatWaited(worst.waited_minutes)}
        </Tag>
      ) : null}

      {stale ? (
        <span className="escalation-banner-more">資料更新失敗，顯示上次結果</span>
      ) : null}
      {!collapsed && hint ? <span className="escalation-banner-more">{hint}</span> : null}

      {!collapsed ? (
        <Button size="small" type="primary" danger={critical} onClick={() => onOpen?.(worst)}>
          查看詳情 <RightOutlined />
        </Button>
      ) : null}

      <Button
        size="small"
        type="text"
        className="escalation-banner-toggle"
        aria-label={collapsed ? "展開警示摘要" : "收合警示摘要"}
        icon={collapsed ? <DownOutlined /> : <UpOutlined />}
        onClick={() => setCollapsed((v) => !v)}
      />
    </div>
  );
}
