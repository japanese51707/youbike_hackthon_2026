import { AlertOutlined, RightOutlined } from "@ant-design/icons";
import { Button, Tag } from "antd";
import { formatWaited } from "../../api/escalationApi.js";

/**
 * ADR-309 L1：跨頁常駐橫幅。有案件等待超過第一個門檻就出現，關不掉——
 * 它要消失只有兩條路：派工，或站況恢復。按「已讀」只會靜音一段時間。
 */
export default function EscalationBanner({ cases, onOpen, hint = "" }) {
  if (!cases.length) return null;
  const worst = cases[0];
  const others = cases.length - 1;

  return (
    <div className={`escalation-banner${worst.stage >= 2 ? " is-critical" : ""}`} role="alert">
      <AlertOutlined className="escalation-banner-icon" />
      <div className="escalation-banner-text">
        <strong>{worst.station_name}</strong>
        <span className="escalation-banner-sub">
          {worst.district}｜{worst.trigger_reason}
        </span>
      </div>
      <Tag color={worst.stage >= 2 ? "red" : "orange"} className="escalation-banner-tag">
        已等 {formatWaited(worst.waited_minutes)}
      </Tag>
      {others > 0 ? <span className="escalation-banner-more">另有 {others} 件</span> : null}
      {hint ? <span className="escalation-banner-more">{hint}</span> : null}
      <Button size="small" type="primary" danger={worst.stage >= 2} onClick={() => onOpen(worst)}>
        立即處理 <RightOutlined />
      </Button>
    </div>
  );
}
