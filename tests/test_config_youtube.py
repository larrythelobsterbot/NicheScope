"""Verify YouTube-related config constants exist and have sane defaults."""
import importlib


def test_youtube_config_defaults(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_DAILY_KEYWORD_BUDGET", raising=False)
    import config
    importlib.reload(config)
    assert config.YOUTUBE_API_KEY == ""
    assert config.YOUTUBE_DAILY_KEYWORD_BUDGET == 99


def test_youtube_schedule_slot():
    import config
    importlib.reload(config)
    assert "youtube" in config.SCHEDULE
    assert config.SCHEDULE["youtube"]["hour"] == 8


def test_youtube_rate_limiter_exists():
    import rate_limiter
    importlib.reload(rate_limiter)
    assert hasattr(rate_limiter, "YOUTUBE")
