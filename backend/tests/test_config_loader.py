from config_loader import reload_config


def test_data_source_mode_env_override(monkeypatch):
    monkeypatch.setenv("YOUBIKE_DATA_SOURCE_MODE", "youbike_official")
    monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
    cfg = reload_config()
    assert cfg["data_source"]["mode"] == "youbike_official"


def test_ecs_defaults_to_s3_relay(monkeypatch):
    monkeypatch.delenv("YOUBIKE_DATA_SOURCE_MODE", raising=False)
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")
    cfg = reload_config()
    assert cfg["data_source"]["mode"] == "youbike_s3"


def test_config_has_data_source(monkeypatch):
    monkeypatch.delenv("YOUBIKE_DATA_SOURCE_MODE", raising=False)
    monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
    cfg = reload_config()
    assert "mode" in cfg["data_source"]
