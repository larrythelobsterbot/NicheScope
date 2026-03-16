#!/bin/bash
# NicheScope Deployment Script
# Runs FROM YOUR LOCAL MACHINE, handles everything over SSH.
#
# Usage: bash scripts/deploy.sh [first-run|update|health|backup|nginx]
#
# first-run: Full setup (dependencies, PM2, Nginx, SSL)
# update:    Just sync code and restart services
# health:    Check VPS status, DB stats, collector logs
# backup:    Download database backup to local machine
# nginx:     Set up or update Nginx config

set -e

# ============================================
# CONFIGURATION (edit these before first run)
# ============================================
VPS_HOST="135.181.248.183"      # e.g. 123.45.67.89 or my-vps (from SSH config)
VPS_USER="root"
REMOTE_DIR="/opt/nichescope"
DOMAIN=""       # set to empty string "" if no domain yet
LOCAL_DIR="."                            # project root (run from nichescope/)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ============================================
# SYNC FILES TO VPS
# ============================================
sync_files() {
    log "Syncing project files to VPS..."

    # Create remote directory structure
    ssh ${VPS_USER}@${VPS_HOST} "mkdir -p ${REMOTE_DIR}/{data,logs,backups}"

    # Rsync everything except build artifacts and local-only files
    rsync -avz --progress \
        --exclude 'node_modules' \
        --exclude '.next' \
        --exclude '__pycache__' \
        --exclude '.git' \
        --exclude '*.pyc' \
        --exclude '.env' \
        --exclude '.env.local' \
        --exclude 'venv' \
        --exclude 'backups' \
        --exclude '.vercel' \
        ${LOCAL_DIR}/ ${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/

    log "Files synced."
}

# ============================================
# FIRST RUN: Full setup
# ============================================
first_run() {
    log "Starting first-time deployment..."

    sync_files

    log "Setting up VPS environment..."
    ssh ${VPS_USER}@${VPS_HOST} << 'REMOTE_SCRIPT'
        set -e

        cd /opt/nichescope

        echo "=== Installing Python dependencies ==="
        pip3 install -r collectors/requirements.txt --break-system-packages 2>/dev/null \
            || pip3 install -r collectors/requirements.txt

        echo "=== Installing Node dependencies ==="
        cd frontend
        npm install --production=false
        cd ..

        echo "=== Building Next.js for production ==="
        cd frontend
        npm run build
        cd ..

        echo "=== Creating .env file template ==="
        if [ ! -f .env ]; then
            cat > .env << 'ENVFILE'
# NicheScope Environment Variables
# Fill in your API keys below

# Turso Database (cloud SQLite for the frontend API routes)
TURSO_DATABASE_URL=
TURSO_AUTH_TOKEN=

# Keepa API (~$21/mo, required for Amazon product data)
KEEPA_API_KEY=

# Amazon Product Advertising API (free with Associates account)
AMAZON_ACCESS_KEY=
AMAZON_SECRET_KEY=
AMAZON_PARTNER_TAG=

# Telegram Bot (for alerts and daily digests)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Alibaba Open API (optional, for supplier auto-discovery)
ALIBABA_APP_KEY=
ALIBABA_APP_SECRET=

# Database path (local SQLite for collectors)
DB_PATH=/opt/nichescope/data/nichescope.db
ENVFILE
            echo "Created .env template. EDIT THIS FILE with your API keys."
        else
            echo ".env already exists, skipping."
        fi

        echo "=== Ensuring directories exist ==="
        mkdir -p data logs backups

        echo "=== Running database migrations ==="
        python3 scripts/migrate_001_collector_health.py

        echo "=== Initializing database (if needed) ==="
        if [ ! -f data/nichescope.db ]; then
            python3 scripts/init_db.py
            python3 scripts/seed_watchlist.py
            echo "Database initialized and seeded."
        else
            echo "Database already exists, skipping init."
        fi

        echo "=== Making scripts executable ==="
        chmod +x collectors/run_scheduler.sh
        chmod +x scripts/setup_cron_backup.sh
        chmod +x scripts/deploy.sh

        echo "=== Setting up PM2 processes ==="

        # Stop existing NicheScope processes if any
        pm2 delete nichescope-web 2>/dev/null || true
        pm2 delete nichescope-collectors 2>/dev/null || true

        # Start using ecosystem config
        pm2 start ecosystem.config.js

        # Save PM2 config (survives reboots)
        pm2 save

        # Set up PM2 startup (auto-start on VPS reboot)
        pm2 startup systemd -u root --hp /root 2>/dev/null || true
        pm2 save

        # Set up log rotation
        pm2 install pm2-logrotate 2>/dev/null || true
        pm2 set pm2-logrotate:max_size 10M
        pm2 set pm2-logrotate:retain 7
        pm2 set pm2-logrotate:compress true

        echo "=== Setting up daily database backup cron ==="
        bash scripts/setup_cron_backup.sh

        echo "=== PM2 processes started ==="
        pm2 status

REMOTE_SCRIPT

    log "VPS setup complete."

    # Set up Nginx if domain is configured
    if [ -n "$DOMAIN" ]; then
        setup_nginx
    else
        warn "No domain configured. Access via http://${VPS_HOST}:3000"
        warn "Set DOMAIN in this script and run: bash scripts/deploy.sh nginx"
    fi

    log ""
    log "============================================"
    log "  DEPLOYMENT COMPLETE"
    log "============================================"
    log ""
    log "Next steps:"
    log "  1. SSH in and edit .env with your API keys:"
    log "     ssh ${VPS_USER}@${VPS_HOST} 'nano ${REMOTE_DIR}/.env'"
    log ""
    log "  2. After editing .env, restart collectors:"
    log "     ssh ${VPS_USER}@${VPS_HOST} 'pm2 restart nichescope-collectors'"
    log ""
    log "  3. Verify everything is running:"
    log "     ssh ${VPS_USER}@${VPS_HOST} 'pm2 status'"
    log ""
    if [ -n "$DOMAIN" ]; then
        log "  Dashboard: https://${DOMAIN}"
    else
        log "  Dashboard: http://${VPS_HOST}:3000"
    fi
    log ""
}

# ============================================
# UPDATE: Just sync and restart
# ============================================
update() {
    log "Updating NicheScope on VPS..."

    sync_files

    ssh ${VPS_USER}@${VPS_HOST} << 'REMOTE_SCRIPT'
        set -e
        cd /opt/nichescope

        echo "=== Running database migrations ==="
        python3 scripts/migrate_001_collector_health.py
        python3 scripts/init_db.py

        echo "=== Installing any new Python dependencies ==="
        pip3 install -r collectors/requirements.txt --break-system-packages 2>/dev/null \
            || pip3 install -r collectors/requirements.txt

        echo "=== Rebuilding frontend ==="
        cd frontend
        npm install --production=false
        npm run build
        cd ..

        echo "=== Restarting all PM2 processes ==="
        pm2 restart nichescope-web
        pm2 restart nichescope-collectors

        echo "=== Current status ==="
        pm2 status

        echo "=== Recent collector logs ==="
        pm2 logs nichescope-collectors --lines 10 --nostream
REMOTE_SCRIPT

    log "Update complete."
}

# ============================================
# NGINX + SSL SETUP
# ============================================
setup_nginx() {
    if [ -z "$DOMAIN" ]; then
        err "No DOMAIN configured. Edit the CONFIGURATION section in this script."
    fi

    log "Configuring Nginx for ${DOMAIN}..."

    # Write the nginx config file (uses variable substitution, not heredoc with quotes)
    ssh ${VPS_USER}@${VPS_HOST} "cat > /etc/nginx/sites-available/nichescope" << NGINXEOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 86400;
    }
}
NGINXEOF

    ssh ${VPS_USER}@${VPS_HOST} << 'REMOTE_NGINX'
        set -e

        # Enable site
        ln -sf /etc/nginx/sites-available/nichescope /etc/nginx/sites-enabled/

        # Test and reload Nginx
        nginx -t && systemctl reload nginx
        echo "Nginx configured and reloaded."

        # SSL with certbot (if available)
        if command -v certbot &> /dev/null; then
            echo "Attempting SSL setup with certbot..."
            certbot --nginx -d $(grep server_name /etc/nginx/sites-available/nichescope | awk '{print $2}' | tr -d ';') \
                --non-interactive --agree-tos --redirect \
                --email admin@$(grep server_name /etc/nginx/sites-available/nichescope | awk '{print $2}' | tr -d ';') \
                2>/dev/null || echo "Certbot needs manual setup. Run: certbot --nginx"
        else
            echo "Certbot not installed. Install with: apt install certbot python3-certbot-nginx"
        fi
REMOTE_NGINX

    log "Nginx setup complete."
}

# ============================================
# HEALTH CHECK
# ============================================
health_check() {
    log "Running health check..."

    ssh ${VPS_USER}@${VPS_HOST} << 'REMOTE_HEALTH'
        echo ""
        echo "=== PM2 Status ==="
        pm2 status

        echo ""
        echo "=== Database Stats ==="
        DB="/opt/nichescope/data/nichescope.db"
        if [ -f "$DB" ]; then
            echo "Keywords:         $(sqlite3 $DB 'SELECT COUNT(*) FROM keywords WHERE is_active = 1;')"
            echo "Categories:       $(sqlite3 $DB 'SELECT COUNT(DISTINCT category) FROM keywords;')"
            echo "Trend data pts:   $(sqlite3 $DB 'SELECT COUNT(*) FROM trend_data;')"
            echo "Products:         $(sqlite3 $DB 'SELECT COUNT(*) FROM products WHERE is_active = 1;')"
            echo "Suppliers:        $(sqlite3 $DB 'SELECT COUNT(*) FROM suppliers;')"
            echo "Pending keywords: $(sqlite3 $DB 'SELECT COUNT(*) FROM pending_keywords WHERE status = "pending";' 2>/dev/null || echo 'N/A')"
            echo "Alerts:           $(sqlite3 $DB 'SELECT COUNT(*) FROM alerts;')"
            echo "Discovery stats:  $(sqlite3 $DB 'SELECT COUNT(*) FROM discovery_stats;' 2>/dev/null || echo 'N/A')"
            echo ""
            echo "Latest trend data:"
            sqlite3 $DB "SELECT keyword_id, date, interest_score FROM trend_data ORDER BY collected_at DESC LIMIT 5;" 2>/dev/null || echo "No trend data yet"
            echo ""
            echo "Collector Health:"
            sqlite3 -header -column $DB "SELECT collector_name, last_success, consecutive_failures, total_runs, total_successes FROM collector_health ORDER BY collector_name;" 2>/dev/null || echo "No health data yet"
        else
            echo "Database not found at $DB"
        fi

        echo ""
        echo "=== Collector Logs (last 20 lines) ==="
        pm2 logs nichescope-collectors --lines 20 --nostream 2>/dev/null || echo "No collector logs yet"

        echo ""
        echo "=== Disk Usage ==="
        du -sh /opt/nichescope/
        du -sh /opt/nichescope/data/ 2>/dev/null || true

        echo ""
        echo "=== Memory Usage ==="
        pm2 jlist | python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    name = p.get('name', 'unknown')
    mem = p.get('monit', {}).get('memory', 0)
    cpu = p.get('monit', {}).get('cpu', 0)
    print(f'  {name}: {mem // 1024 // 1024}MB RAM, {cpu}% CPU')
" 2>/dev/null || echo "Could not parse PM2 metrics"

REMOTE_HEALTH

    log "Health check complete."
}

# ============================================
# BACKUP DATABASE
# ============================================
backup_db() {
    log "Backing up database from VPS..."

    BACKUP_DIR="./backups"
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)

    scp ${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/data/nichescope.db \
        "${BACKUP_DIR}/nichescope_${TIMESTAMP}.db"

    log "Database backed up to ${BACKUP_DIR}/nichescope_${TIMESTAMP}.db"

    # Keep only last 10 backups locally
    ls -t ${BACKUP_DIR}/nichescope_*.db 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
    log "Local backups: $(ls ${BACKUP_DIR}/nichescope_*.db 2>/dev/null | wc -l) files"
}

# ============================================
# MAIN
# ============================================
case "${1:-}" in
    first-run)
        first_run
        ;;
    update)
        update
        ;;
    health)
        health_check
        ;;
    backup)
        backup_db
        ;;
    nginx)
        setup_nginx
        ;;
    *)
        echo "NicheScope Deployment Tool"
        echo ""
        echo "Usage: bash scripts/deploy.sh <command>"
        echo ""
        echo "Commands:"
        echo "  first-run   Full deployment (dependencies, PM2, Nginx, SSL)"
        echo "  update      Sync code changes and restart services"
        echo "  health      Check VPS status, DB stats, collector logs"
        echo "  backup      Download database backup to local machine"
        echo "  nginx       Set up or update Nginx config"
        echo ""
        echo "Before first run, edit the CONFIGURATION section at the top of this script."
        ;;
esac
