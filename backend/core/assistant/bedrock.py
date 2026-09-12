"""Bedrock Converse 薄封裝。金鑰只走環境／IAM，失敗往上丟給 service 降級。"""

from __future__ import annotations

import os

from config_loader import get_config
from core.aws_local import load_local_aws_credentials


def assistant_config() -> dict:
    load_local_aws_credentials()
    cfg = get_config().get("assistant") or {}
    region = (
        os.environ.get("BEDROCK_REGION")
        or cfg.get("bedrock_region")
        or os.environ.get("AWS_REGION")
        or "ap-northeast-1"
    )
    model_id = os.environ.get("BEDROCK_MODEL_ID") or cfg.get("bedrock_model_id") or "amazon.nova-lite-v1:0"
    enabled_env = os.environ.get("BEDROCK_ENABLED")
    if enabled_env is None:
        enabled = bool(cfg.get("enabled", True))
    else:
        enabled = enabled_env.strip().lower() not in {"0", "false", "no", "off"}
    return {
        "enabled": enabled,
        "region": region,
        "model_id": model_id,
        "timeout_sec": int(cfg.get("timeout_sec", 20)),
        "max_tokens": int(cfg.get("max_tokens", 700)),
        "temperature": float(cfg.get("temperature", 0.2)),
    }


def converse_text(*, system: str, messages: list[dict], settings: dict | None = None) -> str:
    """呼叫 Bedrock Converse，回傳純文字。測試可 monkeypatch 此函式。"""
    import boto3
    from botocore.config import Config

    opts = settings or assistant_config()
    creds = {}
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    if access_key and secret:
        creds["aws_access_key_id"] = access_key
        creds["aws_secret_access_key"] = secret
        token = os.environ.get("AWS_SESSION_TOKEN", "").strip()
        if token:
            creds["aws_session_token"] = token
    client = boto3.client(
        "bedrock-runtime",
        region_name=opts["region"],
        config=Config(
            connect_timeout=opts["timeout_sec"],
            read_timeout=opts["timeout_sec"],
            retries={"max_attempts": 1},
        ),
        **creds,
    )
    response = client.converse(
        modelId=opts["model_id"],
        system=[{"text": system}],
        messages=messages,
        inferenceConfig={
            "maxTokens": opts["max_tokens"],
            "temperature": opts["temperature"],
        },
    )
    parts = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise RuntimeError("bedrock_empty")
    return text
