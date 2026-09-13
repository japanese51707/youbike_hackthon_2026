from config_loader import reload_config


def test_data_source_mode_env_override(monkeypatch):
    monkeypatch.setenv("YOUBIKE_DATA_SOURCE_MODE", "youbike_s3")
    cfg = reload_config()
    assert cfg["data_source"]["mode"] == "youbike_s3"


def test_config_defaults_to_official_api(monkeypatch):
    monkeypatch.delenv("YOUBIKE_DATA_SOURCE_MODE", raising=False)
    cfg = reload_config()
    assert cfg["data_source"]["mode"] == "youbike_official"
