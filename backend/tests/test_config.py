from pathlib import Path

from app.core.config import Settings


def test_settings_defaults_match_env_example() -> None:
    s = Settings(_env_file=None)
    assert s.jwt_expire_minutes == 480
    assert s.cloud_cover_max == 30
    assert s.alert_provider == "console"
    assert s.data_dir == Path("./data")
    assert s.cors_origins == ["http://localhost:5173"]


def test_cors_origins_split_from_comma_string() -> None:
    s = Settings(_env_file=None, cors_origins="http://a:1, http://b:2")
    assert s.cors_origins == ["http://a:1", "http://b:2"]


def test_secrets_are_not_printed() -> None:
    s = Settings(_env_file=None, jwt_secret="topsecret")
    assert "topsecret" not in repr(s)
    assert s.jwt_secret_is_placeholder is False
