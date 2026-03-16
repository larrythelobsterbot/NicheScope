#!/bin/bash
# Run this on the VPS to set up automatic daily DB backups
# Usage: bash scripts/setup_cron_backup.sh

BACKUP_DIR="/opt/nichescope/backups"
DB_PATH="/opt/nichescope/data/nichescope.db"

mkdir -p "$BACKUP_DIR"

# Create backup script
cat > /opt/nichescope/scripts/daily_backup.sh << 'BACKUP'
#!/bin/bash
BACKUP_DIR="/opt/nichescope/backups"
DB_PATH="/opt/nichescope/data/nichescope.db"
TIMESTAMP=$(date +%Y%m%d)

if [ ! -f "$DB_PATH" ]; then
    echo "$(date): Database not found at $DB_PATH, skipping backup."
    exit 0
fi

# SQLite safe backup (handles WAL mode)
sqlite3 "$DB_PATH" ".backup '${BACKUP_DIR}/nichescope_${TIMESTAMP}.db'"

# Keep only last 14 days of backups
find "$BACKUP_DIR" -name "nichescope_*.db" -mtime +14 -delete

echo "$(date): Backup complete. $(ls ${BACKUP_DIR}/nichescope_*.db | wc -l) backups stored."
BACKUP

chmod +x /opt/nichescope/scripts/daily_backup.sh

# Add to crontab (runs at 2am daily), replacing any existing nichescope backup entry
(crontab -l 2>/dev/null | grep -v "nichescope.*daily_backup"; echo "0 2 * * * /opt/nichescope/scripts/daily_backup.sh >> /opt/nichescope/logs/backup.log 2>&1") | crontab -

echo "Daily backup cron job installed. Runs at 2am."
echo "Backups stored in: $BACKUP_DIR"
echo "Retention: 14 days"
