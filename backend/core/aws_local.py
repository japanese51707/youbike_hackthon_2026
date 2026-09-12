"""載入專案內的本機 AWS CLI 憑證（secrets/aws-credentials）。不把金鑰寫進程式。"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREDENTIALS = REPO_ROOT / "secrets" / "aws-credentials"

_DEFAULT_MAP = {
    "aws_access_key_id": "AWS_ACCESS_KEY_ID",
    "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY",
    "aws_session_token": "AWS_SESSION_TOKEN",
    "region": "AWS_REGION",
}

_BEDROCK_MAP = {
    "enabled": "BEDROCK_ENABLED",
    "region": "BEDROCK_REGION",
    "model_id": "BEDROCK_MODEL_ID",
}

_PLACEHOLDERS = {"", "YOUR_ACCESS_KEY_ID", "YOUR_SECRET_ACCESS_KEY", "YOUR_SESSION_TOKEN"}


def credentials_path() -> Path:
    override = os.environ.get("YOUBIKE_AWS_CREDENTIALS")
    return Path(override) if override else DEFAULT_CREDENTIALS


def _set_if_empty(name: str, value: str) -> None:
    if not value or value in _PLACEHOLDERS:
        return
    current = os.environ.get(name, "").strip()
    if current:
        return
    os.environ[name] = value


def _clean(value: str) -> str:
    text = (value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip()
    return text


def _read_section(parser: configparser.ConfigParser, section: str) -> dict[str, str]:
    if not parser.has_section(section):
        return {}
    return {key: _clean(parser.get(section, key)) for key in parser.options(section)}


def load_local_aws_credentials(path: Path | None = None) -> dict:
    """讀 INI 憑證檔，填進環境變數（不覆寫已存在的值）。回傳是否載入成功，不含密鑰。"""
    target = Path(path) if path else credentials_path()
    result = {
        "path": str(target),
        "exists": target.is_file(),
        "loaded": False,
        "has_access_key": False,
        "profile": os.environ.get("AWS_PROFILE", "default"),
    }
    if not target.is_file():
        return result

    parser = configparser.ConfigParser()
    parser.read(target, encoding="utf-8")
    profile = result["profile"] if parser.has_section(result["profile"]) else "default"
    result["profile"] = profile
    values = _read_section(parser, profile)
    for key, env_name in _DEFAULT_MAP.items():
        _set_if_empty(env_name, values.get(key, ""))
    bedrock = _read_section(parser, "bedrock")
    for key, env_name in _BEDROCK_MAP.items():
        value = bedrock.get(key, "")
        if value:
            os.environ[env_name] = value

    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    result["has_access_key"] = bool(access_key and access_key not in _PLACEHOLDERS)
    result["loaded"] = result["has_access_key"] and bool(secret and secret not in _PLACEHOLDERS)
    # 此檔含 [bedrock] 與引號，不能當 AWS_SHARED_CREDENTIALS_FILE，否則 boto3 會 ConfigParseError。
    shared = os.environ.get("AWS_SHARED_CREDENTIALS_FILE", "")
    if shared and Path(shared).resolve() == target.resolve():
        os.environ.pop("AWS_SHARED_CREDENTIALS_FILE", None)
    return result
