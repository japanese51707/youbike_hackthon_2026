"""ADR-303: retain last successful observations, never substitute history for live."""
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from .data_source import get_data_source
from .observations import DataUnavailable, normalize, parse_time, record

_lock = RLock()
_last = None
_last_source = None
# ADR-305：記錄最近一次是否降級到 mock 及原因，供 /data/status 呈現「目前顯示模擬資料」。
_mock_fallback_reason = None


def _cfg():
    import os
    from config_loader import get_config
    ds = get_config().get("data_source", {})
    # ADR-305：開發環境(APP_ENV != production)且開關 true 才允許降級 mock；正式環境一律不降。
    dev_env = os.environ.get("APP_ENV", "development") != "production"
    return {
        "mode": ds.get("mode", "mock"),
        "stale_after_sec": ds.get("stale_after_sec", 600),
        "dev_fallback_to_mock": bool(ds.get("dev_fallback_to_mock", False)) and dev_env,
    }


def _mark_mock_fallback(row):
    """ADR-305：把降級用的 mock 站點標記為「上游失敗改用 mock」且不可派工。

    MockDataSource 回傳的 row 已 normalize（data_freshness=mock）。這裡再補上降級原因，
    並強制 dispatch_eligible=False，確保降級 mock 資料不會進入調度決策（守 ADR-303/004 底線）。
    """
    reasons = sorted(set(list(row.get("quality_reasons", [])) + ["upstream_unavailable_using_mock"]))
    row = deepcopy(row)
    row["quality_reasons"] = reasons
    row["dispatch_eligible"] = False
    return row


def _is_stale(source_timestamp, stale_after_sec):
    try:
        age = (datetime.now(timezone.utc) - parse_time(source_timestamp)).total_seconds()
        return age > stale_after_sec or age < -60
    except (ValueError, TypeError):
        return True


def _apply_fault_detection(rows) -> None:
    """ADR-336：對每站跑熱門站故障偵測；命中就就地標記 + 扣除故障後重算空滿率／status。

    扣除規則（owner 定案）：
      - 車故障 L：available_bikes -= L、total_docks -= L（那 L 柱被壞車佔住不能用），扣「一個 L」。
      - 柱故障 M：total_docks -= M、available_docks -= M（那 M 個柱故障還不進）。
    重算 usage_rate 與 status（classify_status）。原始值保留在 raw_* 供顯示「原本 vs 扣除後」。
    只處理 live/mock 且無品質問題的站；扣除後數值夾到合法範圍。
    """
    from core.fault_detection import detect_fault
    from .data_source import classify_status

    for row in rows:
        # 只對可用於決策的即時站況判定（過期/停用/降級站不判，避免誤標）
        if row.get("data_freshness") not in ("live", "mock") or row.get("quality_reasons"):
            continue
        fault = detect_fault(row)
        if not fault:
            continue
        ftype = fault["fault_type"]
        count = int(fault["fault_count"])
        total = int(row.get("total_docks") or 0)
        bikes = int(row.get("available_bikes") or 0)
        docks = int(row.get("available_docks") or 0)
        if total <= 0 or count <= 0:
            continue
        # 保留原始值供前端顯示「原本 → 扣除後」
        row["raw_total_docks"] = total
        row["raw_available_bikes"] = bikes
        row["raw_available_docks"] = docks
        if ftype == "vehicle":
            new_total = max(1, total - count)
            new_bikes = max(0, bikes - count)
            new_docks = min(docks, new_total)          # 可還位不超過新總柱
        else:  # dock
            new_total = max(1, total - count)
            new_bikes = min(bikes, new_total)
            new_docks = max(0, docks - count)
        row["total_docks"] = new_total
        row["available_bikes"] = new_bikes
        row["available_docks"] = new_docks
        row["usage_rate"] = round(new_bikes / new_total * 100, 1) if new_total else 0
        # status 用扣除後站況重判（可能從 normal 升為 low/high/empty/full，反映真實風險）
        if row.get("status") != "offline":
            row["status"] = classify_status(row["usage_rate"], new_bikes, new_docks)
        row["suspected_fault"] = True
        row["fault_type"] = ftype                       # vehicle / dock
        row["fault_count"] = count
        row["fault_reason"] = fault["reason"]


def get_stations_with_degradation(district=None, status=None):
    global _last, _last_source, _mock_fallback_reason
    cfg = _cfg()
    primary = get_data_source()
    source_key = (cfg["mode"], primary)
    with _lock:
        failed = False
        mock_fallback = False
        try:
            rows = primary.get_stations()
            if not rows:
                raise DataUnavailable("資料來源未提供站點快照")
            _last, _last_source = deepcopy(rows), source_key
            _mock_fallback_reason = None
        except Exception as exc:
            if _last_source == source_key and _last:
                # ADR-303：同來源最後成功快照，標 stale。
                rows, failed = deepcopy(_last), True
            elif cfg["dev_fallback_to_mock"]:
                # ADR-305：僅開發環境且開關開，真實源完全取不到時降級到 mock。
                # 降級資料一律標記且不可派工（下方 _mark_mock_fallback）。
                from .mock import MockDataSource
                rows = MockDataSource().get_stations()
                mock_fallback = True
                _mock_fallback_reason = str(exc) or "真實資料來源無法取得"
            else:
                # 正式路徑：無快照回 503，不碰 mock（ADR-303）。
                raise DataUnavailable("站點資料暫時無法取得，請稍後重試") from exc
        if mock_fallback:
            rows = [_mark_mock_fallback(r) for r in rows]
        else:
            rows = [normalize(r, cfg["mode"], cfg["stale_after_sec"], failed=failed) for r in rows]
        record(rows)
    # ADR-324：完整快照才同步空／滿時計；篩選前寫入，避免只看到一區就把他區關案。
    # 故障重算要在此之後——空滿時計看「原始站況」，故障扣除只影響調度/顯示/KPI，不誤觸時計。
    try:
        from core.service_problems import sync_service_problems
        sync_service_problems(rows)
    except Exception as exc:  # noqa: BLE001
        print(f"[service_problems] 同步失敗（不擋站況）：{exc}")
    # ADR-336：熱門站設備故障偵測。命中就標記 + 扣除故障後重算可借/總柱/空滿率/status。
    try:
        _apply_fault_detection(rows)
    except Exception as exc:  # noqa: BLE001
        print(f"[fault_detection] 偵測失敗（不擋站況）：{exc}")
    if district:
        rows = [r for r in rows if r.get("district") == district]
    if status:
        wanted = {s.strip() for s in status.split(",")}
        rows = [r for r in rows if r.get("status") in wanted]
    return rows


def degradation_status():
    cfg = _cfg()
    try:
        rows = get_stations_with_degradation()
        counts = {key: sum(r["data_freshness"] == key for r in rows)
                  for key in ("live", "stale", "historical", "mock")}
        # ADR-305：是否正處於「真實源失敗改用 mock」的降級狀態
        degrading_to_mock = any(
            "upstream_unavailable_using_mock" in r["quality_reasons"] for r in rows)
        return {**cfg, "source": cfg["mode"], "primary_available": not any(
            "upstream_unavailable" in r["quality_reasons"] for r in rows),
            "freshness_counts": counts, "degrading_to_historical": False,
            "degrading_to_mock": degrading_to_mock,
            "mock_fallback_reason": _mock_fallback_reason if degrading_to_mock else None,
            "dispatch_eligible_count": sum(r["dispatch_eligible"] for r in rows)}
    except DataUnavailable:
        return {**cfg, "source": cfg["mode"], "primary_available": False,
                "data_freshness": "unavailable", "degrading_to_historical": False,
                "degrading_to_mock": False, "mock_fallback_reason": None}


def reset():
    global _last, _last_source, _mock_fallback_reason
    with _lock:
        _last = _last_source = None
        _mock_fallback_reason = None
