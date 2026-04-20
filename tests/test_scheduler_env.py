"""Scheduler must fail loudly if .env is missing."""
import importlib
import os
import sys
from pathlib import Path

import pytest


def test_scheduler_exits_when_env_missing(tmp_path, monkeypatch, capsys):
    """Simulate a scheduler startup in a directory with no .env."""
    fake_collectors = tmp_path / "collectors"
    fake_collectors.mkdir()
    # No .env created

    monkeypatch.setattr(sys, "argv", ["scheduler.py"])
    monkeypatch.chdir(tmp_path)

    # Re-import the env-loading helper in isolation
    sys.path.insert(0, str(Path(__file__).parent.parent / "collectors"))
    import scheduler  # noqa
    importlib.reload(scheduler)

    with pytest.raises(SystemExit) as exc_info:
        scheduler.load_env_or_die(fake_collectors / ".env")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert ".env" in captured.err or ".env" in captured.out


def test_scheduler_loads_env_when_present(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("FOO_TEST_VAR=hello\n")

    sys.path.insert(0, str(Path(__file__).parent.parent / "collectors"))
    import scheduler
    importlib.reload(scheduler)

    monkeypatch.delenv("FOO_TEST_VAR", raising=False)
    scheduler.load_env_or_die(env_path)
    assert os.getenv("FOO_TEST_VAR") == "hello"
