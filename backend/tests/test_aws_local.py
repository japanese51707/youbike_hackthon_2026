"""本機 AWS CLI 憑證載入：只測占位符與真實格式，不寫真金鑰。"""
from __future__ import annotations

from pathlib import Path

from core.aws_local import load_local_aws_credentials


def test_placeholder_file_is_not_treated_as_loaded(tmp_path: Path, monkeypatch):
    path = tmp_path / "aws-credentials"
    path.write_text(
        "[default]\naws_access_key_id = YOUR_ACCESS_KEY_ID\naws_secret_access_key = YOUR_SECRET_ACCESS_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    result = load_local_aws_credentials(path)
    assert result["exists"] is True
    assert result["loaded"] is False
    assert "AWS_ACCESS_KEY_ID" not in __import__("os").environ


def test_reads_default_profile_into_env(tmp_path: Path, monkeypatch):
    path = tmp_path / "aws-credentials"
    path.write_text(
        "[default]\n"
        "aws_access_key_id = AKIAEXAMPLETESTKEY\n"
        "aws_secret_access_key = secret-example-not-real\n"
        "region = ap-northeast-1\n"
        "[bedrock]\n"
        "model_id = amazon.nova-lite-v1:0\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    result = load_local_aws_credentials(path)
    assert result["loaded"] is True
    import os
    assert os.environ["AWS_ACCESS_KEY_ID"] == "AKIAEXAMPLETESTKEY"
    assert os.environ["BEDROCK_MODEL_ID"] == "amazon.nova-lite-v1:0"
