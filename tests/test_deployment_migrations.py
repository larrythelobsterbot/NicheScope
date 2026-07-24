import os
import runpy
import shutil
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent.parent
MIGRATIONS = sorted((ROOT / "scripts").glob("migrate_*.py"))


def test_init_and_seed_honor_environment_db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "custom" / "configured.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    init_namespace = runpy.run_path(
        str(ROOT / "scripts" / "init_db.py"), run_name="init_db_probe"
    )
    seed_namespace = runpy.run_path(
        str(ROOT / "scripts" / "seed_watchlist.py"), run_name="seed_watchlist_probe"
    )

    assert Path(init_namespace["DB_PATH"]) == db_path
    assert Path(seed_namespace["DB_PATH"]) == db_path

    init_namespace["init_db"]()
    seed_namespace["seed"]()

    conn = sqlite3.connect(db_path)
    keyword_count = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
    conn.close()
    assert keyword_count > 0


def test_db_path_resolver_uses_env_then_dotenv_then_project_default(
    tmp_path, monkeypatch
):
    resolver_namespace = runpy.run_path(
        str(ROOT / "scripts" / "db_path.py"), run_name="db_path_probe"
    )
    resolve_db_path = resolver_namespace["resolve_db_path"]

    project_root = tmp_path / "project"
    project_root.mkdir()
    dotenv_db = tmp_path / "dotenv db" / "nichescope.sqlite"
    (project_root / ".env").write_text(
        f'DB_PATH="{dotenv_db}" # deployment database\n'
    )

    monkeypatch.delenv("DB_PATH", raising=False)
    assert resolve_db_path(project_root) == dotenv_db

    tab_comment_db = tmp_path / "tab-comment.sqlite"
    (project_root / ".env").write_text(
        f"DB_PATH={tab_comment_db}\t# deployment database\n"
    )
    assert resolve_db_path(project_root) == tab_comment_db

    exported_db = tmp_path / "exported.sqlite"
    (project_root / ".env").write_text(
        f"DB_PATH={tab_comment_db}\n"
        f'export\tDB_PATH="{exported_db}" # final assignment wins\n'
    )
    assert resolve_db_path(project_root) == exported_db

    environment_db = tmp_path / "environment.sqlite"
    monkeypatch.setenv("DB_PATH", str(environment_db))
    assert resolve_db_path(project_root) == environment_db

    monkeypatch.delenv("DB_PATH")
    (project_root / ".env").unlink()
    assert resolve_db_path(project_root) == project_root / "data" / "nichescope.db"


def test_ecosystem_dotenv_parser_matches_resolver_comment_rules(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    ecosystem = project_root / "ecosystem.config.js"
    shutil.copy2(ROOT / "ecosystem.config.js", ecosystem)

    cases = [
        (
            'DB_PATH="/tmp/path with spaces/db.sqlite" # comment\n',
            "/tmp/path with spaces/db.sqlite",
        ),
        ("DB_PATH=/tmp/tab.sqlite\t# comment\n", "/tmp/tab.sqlite"),
        (
            "DB_PATH='/tmp/hash#inside.sqlite' # comment\n",
            "/tmp/hash#inside.sqlite",
        ),
        (
            "DB_PATH=/tmp/first.sqlite\n"
            "export\tDB_PATH='/tmp/final path.sqlite' # comment\n",
            "/tmp/final path.sqlite",
        ),
        (
            "DB_PATH=data/custom.sqlite # project-relative\n",
            str(project_root / "data" / "custom.sqlite"),
        ),
        ("DB_PATH=~/custom.sqlite\n", str(Path.home() / "custom.sqlite")),
        ("DB_PATH=\n", str(project_root / "data" / "nichescope.db")),
    ]
    environment = os.environ.copy()
    environment["DB_PATH"] = "/tmp/inherited-should-not-win.sqlite"
    for dotenv_line, expected in cases:
        (project_root / ".env").write_text(dotenv_line)
        completed = subprocess.run(
            [
                "node",
                "-e",
                "const c=require(process.argv[1]);process.stdout.write(c.apps[0].env.DB_PATH)",
                str(ecosystem),
            ],
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        assert completed.stdout == expected


def test_daily_backup_uses_resolved_dotenv_database(tmp_path):
    project_root = tmp_path / "project with spaces"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "db_path.py", scripts_dir / "db_path.py")
    worker = scripts_dir / "daily_backup.sh"
    shutil.copy2(ROOT / "scripts" / "daily_backup.sh", worker)

    configured_db = project_root / "custom data" / "live.sqlite"
    configured_db.parent.mkdir()
    with sqlite3.connect(configured_db) as conn:
        conn.execute("CREATE TABLE proof (value TEXT NOT NULL)")
        conn.execute("INSERT INTO proof VALUES ('configured database')")
    (project_root / ".env").write_text(
        'DB_PATH="custom data/live.sqlite" # backup source\n'
    )

    environment = os.environ.copy()
    environment["DB_PATH"] = "/tmp/inherited-wrong.sqlite"
    subprocess.run(
        ["bash", str(worker)],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )

    backups = list((project_root / "backups").glob("nichescope_*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT value FROM proof").fetchone()[0] == "configured database"
    assert not (project_root / "data" / "nichescope.db").exists()


def test_backup_setup_installs_project_relative_worker(tmp_path):
    project_root = tmp_path / "project with spaces"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    for name in ("setup_cron_backup.sh", "daily_backup.sh"):
        shutil.copy2(ROOT / "scripts" / name, scripts_dir / name)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "crontab.txt"
    unrelated_entry = '30 1 * * * "/srv/other/daily_backup.sh"\n'
    capture.write_text(unrelated_entry)
    fake_crontab = fake_bin / "crontab"
    fake_crontab.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "-l" ]; then\n'
        '    [ ! -f "$CRONTAB_CAPTURE" ] || cat "$CRONTAB_CAPTURE"\n'
        "    exit 0\n"
        "fi\n"
        'cat > "$CRONTAB_CAPTURE.tmp"\n'
        'mv "$CRONTAB_CAPTURE.tmp" "$CRONTAB_CAPTURE"\n'
    )
    fake_crontab.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["CRONTAB_CAPTURE"] = str(capture)

    for _ in range(2):
        subprocess.run(
            ["bash", str(scripts_dir / "setup_cron_backup.sh")],
            cwd=tmp_path,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

    expected = unrelated_entry + (
        f'0 2 * * * "{scripts_dir / "daily_backup.sh"}" '
        f'>> "{project_root / "logs" / "backup.log"}" 2>&1 '
        "# nichescope-daily-backup\n"
    )
    assert capture.read_text() == expected
    assert os.access(scripts_dir / "daily_backup.sh", os.X_OK)
    assert (project_root / "backups").is_dir()
    assert "/opt/nichescope" not in (
        ROOT / "scripts" / "setup_cron_backup.sh"
    ).read_text()


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
    assert deploy.count(
        'DEPLOY_DB_PATH="$(env -u DB_PATH python3 scripts/db_path.py)"'
    ) == 2
    assert deploy.count(
        'DB_PATH="$DEPLOY_DB_PATH" python3 scripts/init_db.py'
    ) == 2
    assert deploy.count("for migration in scripts/migrate_*.py") == 2
    assert deploy.count(
        'DB_PATH="$DEPLOY_DB_PATH" python3 "$migration"'
    ) == 2
    first_run_block = deploy.split("first_run() {", 1)[1].split(
        "# UPDATE: Just sync and restart", 1
    )[0]
    assert '[ ! -f "$DEPLOY_DB_PATH" ]' in first_run_block
    assert (
        'DB_PATH="$DEPLOY_DB_PATH" python3 scripts/seed_watchlist.py'
        in first_run_block
    )
    assert 'DB_PATH="$DEPLOY_DB_PATH" pm2 start ecosystem.config.js' in first_run_block
    assert (
        "env -u NICHESCOPE_AUTH_USERNAME -u NICHESCOPE_AUTH_PASSWORD "
        'DB_PATH="$DEPLOY_DB_PATH" '
        "pm2 startOrReload ecosystem.config.js --update-env"
    ) in deploy
    update_block = deploy.split("update() {", 1)[1].split("# NGINX + SSL SETUP", 1)[0]
    assert "pm2 restart nichescope-web" not in update_block
    assert "pm2 restart nichescope-collectors" not in update_block
