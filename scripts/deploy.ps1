# NicheScope Deployment Script (PowerShell)
# Runs FROM YOUR WINDOWS MACHINE, handles everything over SSH.
#
# Usage: .\scripts\deploy.ps1 <command>
#
# Commands:
#   first-run   Full setup (dependencies, PM2, Nginx, SSL)
#   update      Sync code changes and restart services
#   health      Check VPS status, DB stats, collector logs
#   backup      Download database backup to local machine
#   refresh     Run all collectors immediately (manual refresh)

param(
    [Parameter(Position=0)]
    [ValidateSet("first-run", "update", "health", "backup", "nginx", "refresh", "refresh-fast", "")]
    [string]$Command
)

# ============================================
# CONFIGURATION (edit these before first run)
# ============================================
$VPS_HOST   = "135.181.248.183"
$VPS_USER   = "root"
$REMOTE_DIR = "/opt/nichescope"
$DOMAIN     = ""  # set if you have a domain

# ============================================
# HELPER FUNCTIONS
# ============================================
function Log($msg)  { Write-Host "[DEPLOY] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN]   $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "[ERROR]  $msg" -ForegroundColor Red; exit 1 }

function Test-SSHAvailable {
    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        Err "ssh not found. Install OpenSSH: Settings > Apps > Optional Features > OpenSSH Client"
    }
    if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
        Err "scp not found. Should come with OpenSSH Client."
    }
}

function Invoke-Remote {
    param([string]$Script)
    # Strip Windows \r characters so Linux doesn't choke on them
    $Script = $Script -replace "`r", ""
    ssh "${VPS_USER}@${VPS_HOST}" $Script
    if ($LASTEXITCODE -ne 0) {
        Warn "Remote command exited with code $LASTEXITCODE"
    }
}

# ============================================
# SYNC FILES TO VPS (using scp recursive)
# ============================================
function Sync-Files {
    Log "Syncing project files to VPS..."

    # Create remote directories
    Invoke-Remote "mkdir -p ${REMOTE_DIR}/{data,logs,backups}"

    # Get project root (where this script lives, one level up)
    $projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.ScriptName)
    if (-not $projectRoot) { $projectRoot = Get-Location }

    # Use scp to sync. Exclude patterns handled by .gitignore on the VPS side.
    # We'll tar locally, send, and extract — much faster than recursive scp.
    Log "Creating archive..."
    $tempArchive = [System.IO.Path]::GetTempFileName() + ".tar.gz"

    # Use tar if available (Windows 10+ has it), otherwise fall back to scp
    if (Get-Command tar -ErrorAction SilentlyContinue) {
        Push-Location $projectRoot
        tar -czf $tempArchive `
            --exclude='node_modules' `
            --exclude='.next' `
            --exclude='__pycache__' `
            --exclude='.git' `
            --exclude='*.pyc' `
            --exclude='.env' `
            --exclude='.env.local' `
            --exclude='venv' `
            --exclude='.vercel' `
            .
        Pop-Location

        Log "Uploading archive..."
        scp $tempArchive "${VPS_USER}@${VPS_HOST}:/tmp/nichescope-update.tar.gz"

        Log "Extracting on VPS..."
        Invoke-Remote "cd ${REMOTE_DIR} && tar -xzf /tmp/nichescope-update.tar.gz && rm /tmp/nichescope-update.tar.gz"

        Remove-Item $tempArchive -ErrorAction SilentlyContinue
    }
    else {
        # Fallback: recursive scp (slower but works everywhere)
        Log "tar not found, using recursive scp (this may be slower)..."
        Push-Location $projectRoot

        # Sync key directories individually
        $dirs = @("collectors", "frontend", "scripts")
        foreach ($dir in $dirs) {
            if (Test-Path $dir) {
                Log "  Syncing $dir/..."
                scp -r "$dir" "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/"
            }
        }

        # Sync root files
        $rootFiles = @("ecosystem.config.js", ".env.example", ".gitignore")
        foreach ($f in $rootFiles) {
            if (Test-Path $f) {
                scp "$f" "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/"
            }
        }

        Pop-Location
    }

    Log "Files synced."
}

# ============================================
# UPDATE: Sync and restart
# ============================================
function Invoke-Update {
    Log "Updating NicheScope on VPS..."

    Sync-Files

    $remoteScript = @"
set -e
cd ${REMOTE_DIR}

echo '=== Running database migrations ==='
python3 scripts/migrate_001_collector_health.py
python3 scripts/init_db.py

echo '=== Seeding new keywords and categories ==='
python3 scripts/seed_watchlist.py

echo '=== Installing any new Python dependencies ==='
pip3 install -r collectors/requirements.txt --break-system-packages 2>/dev/null \
    || pip3 install -r collectors/requirements.txt

echo '=== Rebuilding frontend ==='
cd frontend
npm install --production=false
npm run build
cd ..

echo '=== Restarting all PM2 processes ==='
pm2 restart nichescope-web
pm2 restart nichescope-collectors

echo '=== Current status ==='
pm2 status

echo '=== Recent collector logs ==='
pm2 logs nichescope-collectors --lines 10 --nostream
"@

    Invoke-Remote $remoteScript
    Log "Update complete."
}

# ============================================
# FIRST RUN: Full setup
# ============================================
function Invoke-FirstRun {
    Log "Starting first-time deployment..."

    Sync-Files

    $remoteScript = @"
set -e
cd ${REMOTE_DIR}

echo '=== Installing Python dependencies ==='
pip3 install -r collectors/requirements.txt --break-system-packages 2>/dev/null \
    || pip3 install -r collectors/requirements.txt

echo '=== Installing Node dependencies ==='
cd frontend
npm install --production=false
cd ..

echo '=== Building Next.js for production ==='
cd frontend
npm run build
cd ..

echo '=== Creating .env file template ==='
if [ ! -f .env ]; then
    cp .env.example .env
    echo 'Created .env from template. EDIT THIS FILE with your API keys.'
else
    echo '.env already exists, skipping.'
fi

echo '=== Ensuring directories exist ==='
mkdir -p data logs backups

echo '=== Running database migrations ==='
python3 scripts/migrate_001_collector_health.py
python3 scripts/init_db.py

echo '=== Initializing database (if needed) ==='
if [ ! -f data/nichescope.db ]; then
    python3 scripts/init_db.py
    python3 scripts/seed_watchlist.py
    echo 'Database initialized and seeded.'
else
    echo 'Database already exists, running migrations only.'
fi

echo '=== Making scripts executable ==='
chmod +x collectors/run_scheduler.sh
chmod +x scripts/setup_cron_backup.sh
chmod +x scripts/deploy.sh

echo '=== Setting up PM2 processes ==='
pm2 delete nichescope-web 2>/dev/null || true
pm2 delete nichescope-collectors 2>/dev/null || true
pm2 start ecosystem.config.js
pm2 save
pm2 startup systemd -u root --hp /root 2>/dev/null || true
pm2 save
pm2 install pm2-logrotate 2>/dev/null || true
pm2 set pm2-logrotate:max_size 10M
pm2 set pm2-logrotate:retain 7
pm2 set pm2-logrotate:compress true

echo '=== Setting up daily database backup cron ==='
bash scripts/setup_cron_backup.sh

echo '=== PM2 processes started ==='
pm2 status
"@

    Invoke-Remote $remoteScript

    Log ""
    Log "============================================"
    Log "  DEPLOYMENT COMPLETE"
    Log "============================================"
    Log ""
    Log "Next steps:"
    Log "  1. SSH in and edit .env with your API keys:"
    Log "     ssh ${VPS_USER}@${VPS_HOST} 'nano ${REMOTE_DIR}/.env'"
    Log ""
    Log "  2. After editing .env, restart collectors:"
    Log "     ssh ${VPS_USER}@${VPS_HOST} 'pm2 restart nichescope-collectors'"
    Log ""
    Log "  3. Verify everything is running:"
    Log "     ssh ${VPS_USER}@${VPS_HOST} 'pm2 status'"
    Log ""
    if ($DOMAIN) {
        Log "  Dashboard: https://${DOMAIN}"
    } else {
        Log "  Dashboard: http://${VPS_HOST}:3000"
        Warn "No domain configured. Set `$DOMAIN in this script and run: .\scripts\deploy.ps1 nginx"
    }
}

# ============================================
# HEALTH CHECK
# ============================================
function Invoke-HealthCheck {
    Log "Running health check..."

    $remoteScript = @"
echo ''
echo '=== PM2 Status ==='
pm2 status

echo ''
echo '=== Database Stats ==='
DB='${REMOTE_DIR}/data/nichescope.db'
if [ -f "`$DB" ]; then
    echo "Keywords:         `$(sqlite3 `$DB 'SELECT COUNT(*) FROM keywords WHERE is_active = 1;')"
    echo "Categories:       `$(sqlite3 `$DB 'SELECT COUNT(DISTINCT category) FROM keywords;')"
    echo "Trend data pts:   `$(sqlite3 `$DB 'SELECT COUNT(*) FROM trend_data;')"
    echo "Products:         `$(sqlite3 `$DB 'SELECT COUNT(*) FROM products WHERE is_active = 1;')"
    echo "Suppliers:        `$(sqlite3 `$DB 'SELECT COUNT(*) FROM suppliers;')"
    echo "Pending keywords: `$(sqlite3 `$DB 'SELECT COUNT(*) FROM pending_keywords WHERE status = \"pending\";' 2>/dev/null || echo 'N/A')"
    echo "Alerts:           `$(sqlite3 `$DB 'SELECT COUNT(*) FROM alerts;')"
    echo "Discovery stats:  `$(sqlite3 `$DB 'SELECT COUNT(*) FROM discovery_stats;' 2>/dev/null || echo 'N/A')"
    echo ''
    echo 'Latest trend data:'
    sqlite3 `$DB "SELECT keyword_id, date, interest_score FROM trend_data ORDER BY collected_at DESC LIMIT 5;" 2>/dev/null || echo 'No trend data yet'
    echo ''
    echo 'Collector Health:'
    sqlite3 -header -column `$DB "SELECT collector_name, last_success, consecutive_failures, total_runs, total_successes FROM collector_health ORDER BY collector_name;" 2>/dev/null || echo 'No health data yet'
else
    echo "Database not found at `$DB"
fi

echo ''
echo '=== Collector Logs (last 20 lines) ==='
pm2 logs nichescope-collectors --lines 20 --nostream 2>/dev/null || echo 'No collector logs yet'

echo ''
echo '=== Disk Usage ==='
du -sh ${REMOTE_DIR}/
du -sh ${REMOTE_DIR}/data/ 2>/dev/null || true

echo ''
echo '=== Memory Usage ==='
pm2 jlist | python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    name = p.get('name', 'unknown')
    mem = p.get('monit', {}).get('memory', 0)
    cpu = p.get('monit', {}).get('cpu', 0)
    print(f'  {name}: {mem // 1024 // 1024}MB RAM, {cpu}% CPU')
" 2>/dev/null || echo 'Could not parse PM2 metrics'
"@

    Invoke-Remote $remoteScript
    Log "Health check complete."
}

# ============================================
# BACKUP DATABASE
# ============================================
function Invoke-Backup {
    Log "Backing up database from VPS..."

    $backupDir = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.ScriptName)) "backups"
    if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $localPath = Join-Path $backupDir "nichescope_${timestamp}.db"

    scp "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/data/nichescope.db" $localPath

    Log "Database backed up to $localPath"

    # Keep only last 10 backups
    Get-ChildItem $backupDir -Filter "nichescope_*.db" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 10 | Remove-Item -Force
    $count = (Get-ChildItem $backupDir -Filter "nichescope_*.db").Count
    Log "Local backups: $count files"
}

# ============================================
# NGINX SETUP
# ============================================
function Invoke-NginxSetup {
    if (-not $DOMAIN) { Err "No DOMAIN configured. Edit the CONFIGURATION section in this script." }

    Log "Configuring Nginx for ${DOMAIN}..."

    $nginxConf = @"
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \`$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \`$host;
        proxy_set_header X-Real-IP \`$remote_addr;
        proxy_set_header X-Forwarded-For \`$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \`$scheme;
        proxy_cache_bypass \`$http_upgrade;
        proxy_read_timeout 86400;
    }
}
"@

    # Write nginx config via SSH (strip Windows line endings)
    ($nginxConf -replace "`r", "") | ssh "${VPS_USER}@${VPS_HOST}" "cat > /etc/nginx/sites-available/nichescope"

    $remoteScript = @"
set -e
ln -sf /etc/nginx/sites-available/nichescope /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
echo 'Nginx configured and reloaded.'
if command -v certbot &> /dev/null; then
    echo 'Attempting SSL setup with certbot...'
    certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos --redirect --email admin@${DOMAIN} 2>/dev/null || echo 'Certbot needs manual setup. Run: certbot --nginx'
else
    echo 'Certbot not installed. Install with: apt install certbot python3-certbot-nginx'
fi
"@

    Invoke-Remote $remoteScript
    Log "Nginx setup complete."
}

# ============================================
# REFRESH: Run all collectors now
# ============================================
function Invoke-Refresh {
    param([switch]$Fast)

    if ($Fast) {
        Log "Triggering FAST refresh (skipping slow collectors)..."
        $flags = "--fast"
    } else {
        Log "Triggering FULL refresh of all collectors (this will take ~3.5 hrs)..."
        $flags = ""
    }

    $remoteScript = @"
set -e
cd ${REMOTE_DIR}
python3 scripts/refresh_now.py ${flags}
"@

    Invoke-Remote $remoteScript
    Log "Manual refresh complete."
}

# ============================================
# MAIN
# ============================================
Test-SSHAvailable

switch ($Command) {
    "first-run" { Invoke-FirstRun }
    "update"    { Invoke-Update }
    "health"    { Invoke-HealthCheck }
    "backup"    { Invoke-Backup }
    "nginx"     { Invoke-NginxSetup }
    "refresh"      { Invoke-Refresh }
    "refresh-fast" { Invoke-Refresh -Fast }
    default {
        Write-Host ""
        Write-Host "NicheScope Deployment Tool (PowerShell)" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Usage: .\scripts\deploy.ps1 <command>"
        Write-Host ""
        Write-Host "Commands:"
        Write-Host "  first-run   Full deployment (dependencies, PM2, Nginx, SSL)"
        Write-Host "  update      Sync code changes and restart services"
        Write-Host "  health      Check VPS status, DB stats, collector logs"
        Write-Host "  backup      Download database backup to local machine"
        Write-Host "  nginx       Set up or update Nginx config"
        Write-Host "  refresh       Run ALL collectors (~3.5 hrs)"
        Write-Host "  refresh-fast  Quick refresh: skip slow ones (~45 min)"
        Write-Host ""
    }
}
