#!/usr/bin/env bash
# Install the project-local daily database backup worker in the current user's crontab.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CRON_MARKER="# nichescope-daily-backup"
CRON_ENTRY="0 2 * * * \"$PROJECT_ROOT/scripts/daily_backup.sh\" >> \"$PROJECT_ROOT/logs/backup.log\" 2>&1 $CRON_MARKER"

mkdir -p "$PROJECT_ROOT/data/backups" "$PROJECT_ROOT/logs"
chmod +x "$PROJECT_ROOT/scripts/daily_backup.sh"

(
    crontab -l 2>/dev/null \
        | grep -Fv "$CRON_MARKER" \
        | grep -Fvi "/nichescope/scripts/daily_backup.sh" \
        || true
    printf '%s\n' "$CRON_ENTRY"
) | crontab -

echo "Daily backup cron job installed. Runs at 2am."
echo "Backups stored in: $PROJECT_ROOT/data/backups"
echo "Retention: 14 days"
