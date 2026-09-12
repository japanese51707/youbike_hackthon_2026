"""
空／滿緊急時計獨立收集行程（ADR-320）
====================================
不經 uvicorn、不受 --reload 重啟。持續拉官方站況，寫入 service_clock.db。

本機（已有 youbike-local-dev）::

    docker run -d --name youbike-clock-worker --restart unless-stopped ^
      -v <repo>/backend:/app ^
      -v <repo>/config.yaml:/app/config.yaml ^
      -e YOUBIKE_CONFIG_PATH=/app/config.yaml ^
      -e PYTHONUNBUFFERED=1 ^
      youbike-backend python tools/service_clock_worker.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    from core.service_problems import poll_once, _cfg
    from db.clock_connection import clock_db_path, init_clock_db

    cfg = _cfg()
    if not cfg.get("enabled", True):
        print("[service_clock_worker] service_problems.enabled=false，結束")
        return

    init_clock_db()
    interval = float(cfg.get("輪詢間隔_秒", cfg.get("interval_sec", 60)))
    print(
        f"[service_clock_worker] 啟動，寫入 {clock_db_path()}，間隔 {interval:.0f}s",
        flush=True,
    )
    while True:
        try:
            result = poll_once()
            if not result.get("ok"):
                print(
                    f"[service_clock_worker] 本輪站況失敗（略過）：{result.get('error')}",
                    flush=True,
                )
            elif result.get("pruned"):
                print(
                    f"[service_clock_worker] 清掉窗口外結案 {result['pruned']} 筆",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[service_clock_worker] 本輪錯誤（略過）：{exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
