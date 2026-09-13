"""
設定讀取器（config_loader）
==========================
統一從根目錄 config.yaml 讀取設定，讓所有模組共用同一份設定來源。
呼應設計原則：所有閾值/權重外部化，不寫死在程式碼（D8 / steering §3）。

用法：
    from config_loader import get_config
    cfg = get_config()
    threshold = cfg["trigger"]["安全緩衝_台數"]
"""

from pathlib import Path
import os
import yaml

# config.yaml 預設在專案根目錄（backend 的上一層）；
# Docker 或特殊部署可用環境變數 YOUBIKE_CONFIG_PATH 覆寫。
_CONFIG_PATH = Path(os.environ.get(
    "YOUBIKE_CONFIG_PATH",
    Path(__file__).parent.parent / "config.yaml",
))

_cache = None


def _apply_env_overrides(cfg: dict) -> dict:
    """本機預設直連官方；雲端 ECS 自動改走 S3 中繼（ADR-332）。"""
    ds = cfg.setdefault("data_source", {})
    mode = os.environ.get("YOUBIKE_DATA_SOURCE_MODE", "").strip()
    if mode:
        ds["mode"] = mode
    elif os.environ.get("AWS_EXECUTION_ENV", "").startswith("AWS_ECS"):
        ds["mode"] = "youbike_s3"
    return cfg


def get_config() -> dict:
    """讀取並快取 config.yaml。修改設定檔後需重啟服務才生效。"""
    global _cache
    if _cache is None:
        if not _CONFIG_PATH.exists():
            raise FileNotFoundError(f"找不到設定檔：{_CONFIG_PATH}")
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _cache = _apply_env_overrides(yaml.safe_load(f) or {})
    return _cache


def reload_config() -> dict:
    """強制重新讀取（測試或熱更新用）。"""
    global _cache
    _cache = None
    return get_config()
