"""Shared pytest fixtures for NicheScope integration tests."""
import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure collectors/ and scripts/ are importable from tests
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "collectors"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """A fresh SQLite DB with NicheScope schema + all migrations applied."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    # init_db.py captures DB_PATH at import with no env fallback, so we
    # import it, override DB_PATH on the module, and call init_db() directly.
    import init_db as _init
    _init.DB_PATH = str(db_path)
    _init.init_db()

    # migrate_001_collector_health.py reads DB_PATH from env at import, so
    # reloading after monkeypatch.setenv is sufficient.
    import migrate_001_collector_health as _m1
    importlib.reload(_m1)
    _m1.migrate()
    # Task 2's migration is applied by tests that need it (not all do).

    # config MUST be reloaded first - collectors bind `from config import DB_PATH`
    # at their module top, so they need a fresh config.DB_PATH before their
    # own reload re-imports it.
    if "config" in sys.modules:
        importlib.reload(sys.modules["config"])

    collectors_dir = str(ROOT / "collectors")
    for name, module in list(sys.modules.items()):
        if name == "config":
            continue
        module_file = getattr(module, "__file__", None) or ""
        if module_file.startswith(collectors_dir):
            importlib.reload(module)

    return str(db_path)


def require_env(var_name):
    """Skip the test if the given env var is not set or empty."""
    val = os.getenv(var_name, "")
    if not val:
        pytest.skip(f"{var_name} not set; skipping integration test")
    return val
