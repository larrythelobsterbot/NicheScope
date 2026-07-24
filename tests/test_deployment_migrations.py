import runpy
import sqlite3
from pathlib import Path


ROOT = Path(__file__).parent.parent
MIGRATIONS = sorted((ROOT / "scripts").glob("migrate_*.py"))


def test_full_migration_chain_and_init_are_idempotent(temp_db):
    for migration in MIGRATIONS:
        runpy.run_path(str(migration), run_name="__main__")

    # init_db is also invoked by update deployments and must remain safe after
    # migration 002 replaces tiktok_trends with a compatibility view.
    import init_db  # pyright: ignore[reportMissingImports]

    init_db.init_db()
    for migration in MIGRATIONS:
        runpy.run_path(str(migration), run_name="__main__")

    conn = sqlite3.connect(temp_db)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(collector_health)")}
    conn.close()
    assert {"items_collected", "last_status", "consecutive_zero_runs"} <= columns


def test_deploy_runs_every_migration_on_first_run_and_update():
    deploy = (ROOT / "scripts" / "deploy.sh").read_text()
    assert deploy.count("for migration in scripts/migrate_*.py") == 2
    assert deploy.count(
        'DB_PATH="${DB_PATH:-data/nichescope.db}" python3 "$migration"'
    ) == 2
