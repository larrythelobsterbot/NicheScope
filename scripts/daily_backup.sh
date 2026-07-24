#!/usr/bin/env bash
# Create a safe daily backup of the database configured in the project .env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/backups"
DB_PATH="$(env -u DB_PATH python3 "$SCRIPT_DIR/db_path.py")"
TIMESTAMP="$(date +%Y%m%d)"
BACKUP_FILE="$BACKUP_DIR/nichescope_${TIMESTAMP}.db"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "$(date): Database not found at $DB_PATH, skipping backup."
    exit 0
fi

DB_PATH="$DB_PATH" BACKUP_FILE="$BACKUP_FILE" python3 - <<'PY'
import os
import sqlite3
from pathlib import Path

source_path = Path(os.environ["DB_PATH"])
backup_path = Path(os.environ["BACKUP_FILE"])
temporary_path = backup_path.with_suffix(backup_path.suffix + ".tmp")
temporary_path.unlink(missing_ok=True)

source = sqlite3.connect(source_path)
destination = sqlite3.connect(temporary_path)
try:
    source.backup(destination)
    integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"backup integrity check failed: {integrity}")
finally:
    destination.close()
    source.close()

os.replace(temporary_path, backup_path)
PY

find "$BACKUP_DIR" -name "nichescope_*.db" -mtime +14 -delete
BACKUP_COUNT="$(find "$BACKUP_DIR" -name 'nichescope_*.db' -type f | wc -l)"
echo "$(date): Backup complete. $BACKUP_COUNT backups stored in $BACKUP_DIR."
