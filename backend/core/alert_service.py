"""
警示服務（core.alert_service）— 題目差異化亮點
================================================
題目明確點名「現行機關系統無警示通知功能」，這是我們的差異化亮點。

職責：
  1. 從站點狀態 + 調度建議產生警示（分級 info/warning/critical）
  2. acknowledge 標記已讀
  3. webhook 訂閱 + 出向推播（給機關系統，含出向資安驗證）
  4. SSE 串流佇列（給前端即時跳警示）

不做：觸發判斷本身（借用 rule_engine 的建議）、預測。

分級規則（對齊 alert.py AlertLevel）：
  - critical：已空站/已滿站（現況已出問題），或建議 priority_level=high
  - warning ：預測即將空/滿（還沒發生），或建議 priority_level=medium
  - info    ：一般提示

出向資安（steering §11 出向信任）：webhook 推播是「我方主動打第三方」，
  - callback_url 必須 https、不得指向內網/本機（防 SSRF）
  - 設超時、限制重試，失敗記錄但不無限重試
  - 帶訂閱時登記的 token 供對方驗證來源
  - 不把系統內部錯誤細節塞進 webhook payload

儲存：記憶體版，A5 接 SQLite。
"""

from __future__ import annotations
import datetime as _dt
import ipaddress
import urllib.parse
from typing import Optional


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def classify_alert_level(station: dict, recommendation: Optional[dict] = None) -> Optional[str]:
    """依站點現況 + 調度建議決定警示等級。無需警示回 None。"""
    status = station.get("status")
    # 現況已出問題 → critical
    if status in ("empty", "full"):
        return "critical"
    # 有調度建議 → 依優先級
    if recommendation:
        level = recommendation.get("priority_level")
        if level == "high":
            return "critical"
        if level == "medium":
            return "warning"
        return "info"
    # 無建議、非空滿 → 不警示
    return None


def _is_safe_callback_url(url: str) -> tuple[bool, str]:
    """出向 SSRF 防護：只允許 https 且非內網/本機的 callback。

    回 (是否安全, 原因)。這是出向資安關鍵（steering §11）。
    """
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False, "URL 解析失敗"
    if p.scheme != "https":
        return False, "callback_url 必須為 https"
    host = p.hostname or ""
    if not host:
        return False, "缺少主機名"
    # 擋 localhost / 內網 IP（防 SSRF 打內部服務）
    if host in ("localhost", "127.0.0.1", "::1"):
        return False, "不可指向本機"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False, "不可指向內網/私有位址"
    except ValueError:
        pass  # host 是網域名（非 IP），可接受
    return True, "ok"


class AlertService:
    def __init__(self, audit=None):
        # alerts / subscriptions 存 SQLite（db.alerts_repo）；
        # SSE 佇列留記憶體（短暫推送緩衝，重啟消失無妨，前端會重連）
        self._sse_queue: list[dict] = []
        import uuid
        self._uuid = uuid
        if audit is None:
            from .audit import get_audit_service
            audit = get_audit_service()
        self._audit = audit

    # ── 產生警示 ──
    def generate_from_stations(
        self,
        stations: list[dict],
        recommendations: Optional[list[dict]] = None,
    ) -> list[dict]:
        """掃描站點，產生警示清單。recommendations 供分級與建議動作。"""
        from db import alerts_repo
        rec_by_id = {r["station_id"]: r for r in (recommendations or [])}
        # 已有「未讀」警示的站，不重複產生（去重：同站同等級一次就好）
        existing = alerts_repo.unacked_station_levels()
        new_alerts = []
        for st in stations:
            rec = rec_by_id.get(st.get("station_id"))
            level = classify_alert_level(st, rec)
            if level is None:
                continue
            if (st.get("station_id"), level) in existing:
                continue   # 該站該等級已有未讀警示，跳過
            new_alerts.append(self._create_alert(st, level, rec))
        return new_alerts

    def _create_alert(self, station: dict, level: str, rec: Optional[dict]) -> dict:
        from db import alerts_repo
        ts = _now_iso()
        suffix = self._uuid.uuid4().hex[:8]
        name = station.get("station_name", "")
        status = station.get("status")
        if status == "empty":
            msg = f"{name} 已空站（無車可借），建議立即補車"
        elif status == "full":
            msg = f"{name} 已滿站（無位可還），使用者無法還車"
        elif rec:
            msg = f"{name}{rec.get('reason', '需注意')}"
        else:
            msg = f"{name}狀態需注意"
        alert = {
            "alert_id": f"ALERT-{ts.replace(':', '').replace('-', '')}-{suffix}",
            "level": level,
            "station_id": station.get("station_id", ""),
            "station_name": name,
            "district": station.get("district", ""),
            "message": msg,
            "triggered_at": ts,
            "suggested_action": (f"{rec['action']} {rec['quantity']} 台" if rec else None),
            "acknowledged": False,
        }
        alerts_repo.insert_alert(alert)
        self._sse_queue.append(alert)          # 排入 SSE 佇列（記憶體）
        self._dispatch_webhooks(alert)          # 主動推播給機關
        return alert

    # ── 查詢 / 確認 ──
    def list_alerts(self, level: Optional[str] = None,
                    acknowledged: Optional[bool] = None) -> list[dict]:
        from db import alerts_repo
        return alerts_repo.list_alerts(level=level, acknowledged=acknowledged)

    def acknowledge(self, alert_id: str) -> Optional[dict]:
        from db import alerts_repo
        return alerts_repo.acknowledge(alert_id)

    # ── webhook 訂閱（出向資安）──
    def subscribe(self, callback_url: str, levels: list[str],
                  districts: list[str], token: Optional[str] = None) -> dict:
        """機關登記 webhook。callback_url 先過 SSRF 檢查，不安全就拒絕。"""
        from db import alerts_repo
        safe, why = _is_safe_callback_url(callback_url)
        if not safe:
            raise ValueError(f"callback_url 未通過出向安全檢查：{why}")
        sub = {
            "subscription_id": f"SUB-{alerts_repo.count_subscriptions() + 1:04d}",
            "callback_url": callback_url,
            "levels": levels,
            "districts": districts,
            "token": token,
        }
        alerts_repo.insert_subscription(sub)
        return sub

    def _dispatch_webhooks(self, alert: dict) -> None:
        """把警示推給符合條件的訂閱者。實際 HTTP 送出在此（骨架先只挑選對象）。

        真正送出時要：帶 token、設超時、限制重試、payload 不含內部細節。
        A3 骨架先做「挑對象 + 記錄」，實際 httpx.post 待正式串接（現場才有真 URL）。
        """
        from db import alerts_repo
        for sub in alerts_repo.list_subscriptions():
            if alert["level"] not in sub["levels"]:
                continue
            if sub["districts"] and alert["district"] not in sub["districts"]:
                continue
            # TODO(正式串接)：httpx.post(sub["callback_url"], json=payload,
            #   headers={"X-Alert-Token": sub["token"]}, timeout=5)
            #   失敗記錄、最多重試 N 次、不外洩內部錯誤
            pass

    # ── SSE 串流 ──
    def drain_sse(self) -> list[dict]:
        """取出並清空 SSE 待推佇列（前端輪詢/串流時呼叫）。"""
        out = list(self._sse_queue)
        self._sse_queue.clear()
        return out


# ── 模組級單例 ──
_service: Optional[AlertService] = None


def get_alert_service() -> AlertService:
    global _service
    if _service is None:
        _service = AlertService()
    return _service


def reset_alert_service() -> None:
    global _service
    _service = None
