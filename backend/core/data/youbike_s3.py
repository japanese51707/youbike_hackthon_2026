"""
YouBike 官方站況（經 S3 中繼）資料源 — ADR-332
=============================================
雲端 ECS（us-east-1，境外 IP）直連台灣官方 data.ntpc.gov.tw 會被官方端封鎖
（ConnectError: Network is unreachable / SSL handshake timeout）。B 方案解法：

  台灣端中繼（tools/relay_stations_to_s3.py，跑在能連官方的台灣機器）
    → 定時抓官方 CSV → 上傳 S3：s3://<bucket>/<key>（預設 live/stations_latest.csv）
  雲端後端（本資料源）
    → 從同帳號 S3 讀該 CSV（走 task role，快且不受官方封鎖）→ 轉標準站況格式

本類別繼承 YouBikeOfficialDataSource，只覆寫「原始資料怎麼來」（_fetch_raw）：
官方是 HTTPS 抓 CSV，這裡改成 S3 GetObject 抓同一份 CSV，其餘解析／驗證／快取／
退避／欄位轉換（_to_standard）全部沿用官方源，確保兩者產出完全一致的標準欄位。

config（data_source 區塊）：
  s3_bucket           中繼上傳的 bucket（沿用歷史資料同一個）
  live_s3_key         中繼上傳的物件 key（預設 live/stations_latest.csv）
  s3_max_age_sec      S3 物件超過此秒數視為過期（中繼掛掉時不供應過期資料；預設 900=15分）
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .observations import DataUnavailable
from .youbike_official import YouBikeOfficialDataSource

_DEFAULT_KEY = "live/stations_latest.csv"
_DEFAULT_MAX_AGE = 900  # 15 分鐘：官方約 5-10 分更新，中繼正常時遠比這新；超過視為中繼異常


class YouBikeS3DataSource(YouBikeOfficialDataSource):
    name = "youbike_s3"

    def __init__(self):
        # 不呼叫父類 __init__（那會驗證官方 HTTPS URL）；自行初始化所需欄位。
        from config_loader import get_config
        from threading import RLock

        ds = get_config().get("data_source", {})
        self._bucket = ds.get("s3_bucket")
        self._key = ds.get("live_s3_key") or _DEFAULT_KEY
        self._max_age = int(ds.get("s3_max_age_sec", _DEFAULT_MAX_AGE))
        # 沿用父類的快取／退避參數（讓 _load 行為一致）
        self._refresh = max(ds.get("min_refresh_sec", 60), ds.get("refresh_interval_sec", 120))
        self._timeout = ds.get("timeout_sec", 30)
        self._max_bytes = ds.get("max_response_bytes", 5_000_000)
        self._backoff = ds.get("retry_backoff_sec", 30)
        self._cache = []
        self._cache_at = None
        self._retry_at = 0
        self._lock = RLock()
        if not self._bucket:
            raise ValueError("youbike_s3 資料源需設定 data_source.s3_bucket")

    def _s3_client(self):
        import boto3
        region = None
        try:
            from config_loader import get_config
            region = get_config().get("aws", {}).get("region")
        except Exception:  # noqa: BLE001
            region = None
        return boto3.client("s3", region_name=region) if region else boto3.client("s3")

    def _fetch_raw(self):
        """從 S3 讀中繼上傳的官方 CSV，回 list[dict]（欄位同官方 CSV）。

        物件過舊（超過 s3_max_age_sec，代表中繼可能掛了）→ 視為不可用，
        不供應過期資料（交由上層 degradation 走 stale 快照或 503）。
        """
        import botocore.exceptions

        client = self._s3_client()
        try:
            obj = client.get_object(Bucket=self._bucket, Key=self._key)
        except botocore.exceptions.ClientError as exc:
            raise DataUnavailable(f"S3 站況物件讀取失敗：{exc}") from exc

        # 新鮮度檢查：物件最後修改時間距現在不可超過 max_age。
        last_modified = obj.get("LastModified")
        if last_modified is not None:
            age = (datetime.now(timezone.utc) - last_modified).total_seconds()
            if age > self._max_age:
                raise DataUnavailable(
                    f"S3 站況物件已過期（{age:.0f}s > {self._max_age}s），中繼可能未運作")

        body = obj["Body"].read(self._max_bytes + 1)
        if len(body) > self._max_bytes:
            raise DataUnavailable("S3 站況物件超過大小限制")
        return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
