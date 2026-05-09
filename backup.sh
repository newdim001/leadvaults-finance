#!/bin/bash
# Lead Vaults Finance — Enhanced Backup Script
# Features: DB integrity check, hot backup, uploads backup, 
#            remote sync to Hetzner, Telegram notification
set -e

# ─── Config ───
BACKUP_DIR="/Users/suren/family-finance/backups"
DB_PATH="/Users/suren/family-finance/data/finance.db"
UPLOADS_DIR="/Users/suren/family-finance/uploads"
FRONTEND_DIR="/Users/suren/family-finance/frontend"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/finance_$TIMESTAMP"
REMOTE_DIR="/root/finance-backups"
REMOTE_HOST="root@62.238.12.115"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup..." >> "$BACKUP_DIR/backup.log"

# ─── Step 1: DB Integrity Check ───
echo "Running DB integrity check..."
INTEGRITY=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>&1)
if [ "$INTEGRITY" != "ok" ]; then
    echo "ERROR: Database integrity check FAILED: $INTEGRITY" | tee -a "$BACKUP_DIR/backup.log"
    # Still attempt backup but flag as suspect
    BACKUP_FLAG="DAMAGED"
else
    echo "DB integrity: OK"
    BACKUP_FLAG="OK"
fi

# ─── Step 2: Vacuum DB (optimize) ───
echo "Vacuuming database..."
sqlite3 "$DB_PATH" "VACUUM;"

# ─── Step 3: Hot Backup DB ───
echo "Creating database snapshot..."
sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}.db'"
gzip -f "${BACKUP_FILE}.db"

# ─── Step 4: Backup Uploads (receipts) ───
if [ -d "$UPLOADS_DIR" ] && [ "$(ls -A $UPLOADS_DIR 2>/dev/null)" ]; then
    echo "Backing up uploads directory..."
    tar czf "${BACKUP_FILE}_uploads.tar.gz" -C "$(dirname $UPLOADS_DIR)" "$(basename $UPLOADS_DIR)" 2>/dev/null
    UPLOADS_BACKUP="yes"
else
    UPLOADS_BACKUP="no"
    echo "No uploads to backup"
fi

# ─── Step 5: Local Retention (30 days) ───
echo "Rotating local backups (keeping 30)..."
ls -t "$BACKUP_DIR"/finance_*.db.gz 2>/dev/null | tail -n +31 | xargs -r rm
ls -t "$BACKUP_DIR"/finance_*_uploads.tar.gz 2>/dev/null | tail -n +31 | xargs -r rm

# ─── Step 6: Remote Sync to Hetzner (90 days retention) ───
echo "Syncing to Hetzner server..."
scp -q -o ConnectTimeout=10 "${BACKUP_FILE}.db.gz" "${REMOTE_HOST}:${REMOTE_DIR}/" 2>/dev/null && \
    REMOTE_OK="yes" || REMOTE_OK="no"

if [ "$UPLOADS_BACKUP" = "yes" ]; then
    scp -q -o ConnectTimeout=10 "${BACKUP_FILE}_uploads.tar.gz" "${REMOTE_HOST}:${REMOTE_DIR}/" 2>/dev/null || true
fi

# Clean old remote backups (90 days)
ssh -o ConnectTimeout=10 "$REMOTE_HOST" \
    "find $REMOTE_DIR -name 'finance_*.db.gz' -mtime +90 -delete" 2>/dev/null || true

# ─── Step 7: Backup Log ───
BACKUP_SIZE=$(du -h "${BACKUP_FILE}.db.gz" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete: ${BACKUP_FILE}.db.gz (${BACKUP_SIZE}) | INTEGRITY=${BACKUP_FLAG} | REMOTE=${REMOTE_OK}" | tee -a "$BACKUP_DIR/backup.log"

# ─── Step 8: Rotate log ───
tail -100 "$BACKUP_DIR/backup.log" > "$BACKUP_DIR/backup.log.tmp" && mv "$BACKUP_DIR/backup.log.tmp" "$BACKUP_DIR/backup.log"

# ─── Step 9: Quick health check (server process alive) ───
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:8000/ 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ] || [ "$HEALTH" = "302" ] || [ "$HEALTH" = "301" ]; then
    echo "App health: OK (HTTP $HEALTH)"
else
    echo "WARNING: App health check returned HTTP $HEALTH — app may be down on port 8000" | tee -a "$BACKUP_DIR/backup.log"
fi

echo ""
echo "✅ Backup complete — DB: ${BACKUP_SIZE} | Integrity: ${BACKUP_FLAG} | Remote: ${REMOTE_OK}"
