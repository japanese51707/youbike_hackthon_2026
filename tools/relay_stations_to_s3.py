#!/usr/bin/env python3
"""
台灣端站況中繼上傳 S3 — ADR-332（B 方案）
==========================================
雲端 ECS（us-east-1 境外 IP）直連台灣官方 data.ntpc.gov.tw 被官方端封鎖。
本腳本跑在「能連官方的台灣機器」（demo 期間你的本機），定時抓官方即時站況 CSV，
原封不動上傳到 S3；雲端後端資料源 youbike_s3 再從 S3 讀（走 task role，快且不被封鎖）。

用法（在專案根目錄，帶好 AWS 憑證與 profile）：
    AWS_PROFILE=hackathon AWS_REGION=us-east-1 \
      .venv/bin/python3.14 tools/relay_stations_to_s3.py            # 每 interval 秒持續上傳
    ... tools/relay_stations_to_s3.py --once                        # 只上傳一次（測試用）
    ... tools/relay_stations_to_s3.py --interval 120                # 自訂間隔（秒）

參數（可用環境變數覆寫）：
    RELAY_BUCKET   S3 bucket（預設讀 config.yaml data_source.s3_bucket）
    RELAY_KEY      上傳 key（預設 live/stations_latest.csv）
    RELAY_INTERVAL 上傳間隔秒數（預設 120，對齊官方約 5-10 分更新，勤一點確保新鮮）

原則：只上傳「驗證通過、站數合理」的完整 CSV；抓取失敗就跳過本輪（不覆蓋 S3 上一份
好資料），避免把壞資料推上雲端。
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 讓 import backend 模組（沿用官方源的抓取與驗證邏輯）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_DEFAULT_KEY = "live/stations_latest.csv"


def _config():
    from config_loader import get_config
    return get_config().get("data_source", {})


def _fetch_official_csv_bytes(timeout: int) -> bytes:
    """抓官方即時站況 CSV 原始 bytes（不轉換，讓雲端拿到與官方一致的原始檔）。

    複用官方源的 SSL/URL 設定，確保與後端直連官方時同一份資料格式。
    """
    import httpx
    import ssl
    import certifi

    ds = _config()
    url = ds.get("youbike_official_url") or (
        "https://data.ntpc.gov.tw/api/datasets/"
        "010e5b15-3823-4b20-b401-b1cf000550c5/csv/file")
    max_bytes = int(ds.get("max_response_bytes", 5_000_000))

    context = ssl.create_default_context(cafile=certifi.where())
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT  # 官方憑證鏈相容（同 youbike_official）
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=False, verify=context) as resp:
        resp.raise_for_status()
        body = bytearray()
        for chunk in resp.iter_bytes():
            body.extend(chunk)
            if len(body) > max_bytes:
                raise RuntimeError("官方資料超過大小限制")
    return bytes(body)


def _validate_csv(raw: bytes) -> int:
    """用後端官方源的 _to_standard 驗證這份 CSV 能解析出合理站數。回站數；不合理拋例外。"""
    import csv
    from core.data.youbike_official import YouBikeOfficialDataSource

    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    parsed = [s for r in rows if (s := YouBikeOfficialDataSource._to_standard(r)) is not None]
    if not parsed or len(parsed) < 500:  # 新北 1600+ 站，解析出太少代表抓到壞資料
        raise RuntimeError(f"CSV 驗證未通過（raw={len(rows)} parsed={len(parsed)}）")
    return len(parsed)


def _upload(bucket: str, key: str, raw: bytes) -> None:
    import boto3
    region = os.environ.get("AWS_REGION") or _config().get("region")
    client = boto3.client("s3", region_name=region) if region else boto3.client("s3")
    client.put_object(
        Bucket=bucket, Key=key, Body=raw,
        ContentType="text/csv",
        Metadata={"uploaded_at": datetime.now(timezone.utc).isoformat()})


def relay_once(bucket: str, key: str, timeout: int) -> bool:
    try:
        raw = _fetch_official_csv_bytes(timeout)
        count = _validate_csv(raw)
        _upload(bucket, key, raw)
        print(f"[relay] {datetime.now().strftime('%H:%M:%S')} 上傳成功："
              f"{count} 站、{len(raw)} bytes → s3://{bucket}/{key}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[relay] {datetime.now().strftime('%H:%M:%S')} 本輪失敗（略過，不覆蓋 S3）：{exc}")
        return False


def main():
    ap = argparse.ArgumentParser(description="台灣端站況中繼上傳 S3（ADR-332 B 方案）")
    ap.add_argument("--once", action="store_true", help="只上傳一次就結束")
    ap.add_argument("--interval", type=int,
                    default=int(os.environ.get("RELAY_INTERVAL", 120)),
                    help="上傳間隔秒數（預設 120）")
    ap.add_argument("--timeout", type=int, default=int(_config().get("timeout_sec", 30)),
                    help="抓官方逾時秒數（預設沿用 config）")
    args = ap.parse_args()

    bucket = os.environ.get("RELAY_BUCKET") or _config().get("s3_bucket")
    key = os.environ.get("RELAY_KEY") or _config().get("live_s3_key") or _DEFAULT_KEY
    if not bucket:
        print("錯誤：找不到 S3 bucket（設 RELAY_BUCKET 或 config data_source.s3_bucket）")
        sys.exit(1)

    print(f"[relay] 中繼啟動：官方站況 → s3://{bucket}/{key}"
          f"（{'單次' if args.once else f'每 {args.interval}s'}，逾時 {args.timeout}s）")
    if args.once:
        sys.exit(0 if relay_once(bucket, key, args.timeout) else 1)

    while True:
        relay_once(bucket, key, args.timeout)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
