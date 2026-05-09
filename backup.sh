#!/bin/bash
# Lead Vaults Finance — Production Backup Script
# DB integrity → Hot backup → GPG encrypt → Uploads → Remote sync → Telegram alert
set -e

# ─── Config ───
BACKUP_DIR="/Users/suren/family-finance/backups"
DB_PATH="/Users/suren/family-finance/data/finance.db"
UPLOADS_DIR="/Users/suren/family-finance/uploads"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/finance_$TIMESTAMP"
REMOTE_DIR="/root/finance-backups"
REMOTE_HOST="root@62.238.12.115"

# Telegram — uses Hermes Agent's bot if available
TG_BOT_TOKEN=""
TG_CHAT_ID=""
# NOTE: To enable Telegram alerts, set TG_BOT_TOKEN and TG_CHAT_ID above

mkdir -p "$BACKUP_DIR"
LOG="$BACKUP_DIR/backup.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⏱ Starting backup..." >> "$LOG"

# ─── Helper: send Telegram message ───
tg_notify() {
    local msg="$1"
    if [ -n "$TG_BOT_TOKEN" ] && [ -n "$TG_CHAT_ID" ]; then
        curl -s -o /dev/null "https://api.telegram.org/bot$TG_BOT_TOKEN/sendMessage" \
            -d "chat_id=$TG_CHAT_ID" -d "text=$msg" -d "disable_notification=true" 2>/dev/null || true
    fi
}

# ─── Step 1: DB Integrity Check ───
INTEGRITY=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>&1)
if [ "$INTEGRITY" != "ok" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ INTEGRITY FAILED: $INTEGRITY" >> "$LOG"
    tg_notify "❌ Lead Vaults backup FAILED — DB integrity check failed: $INTEGRITY"
    exit 1
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Integrity: OK" >> "$LOG"

# ─── Step 2: Vacuum DB ───
sqlite3 "$DB_PATH" "VACUUM;"

# ─── Step 3: Hot Backup DB ───
sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}.db'"

# ─── Step 4: GPG Encrypt ───
/opt/homebrew/bin/gpg --yes --batch --recipient backup@leadvaults.io \
    --encrypt --output "${BACKUP_FILE}.db.gpg" "${BACKUP_FILE}.db" 2>/dev/null
rm -f "${BACKUP_FILE}.db"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ GPG encrypted" >> "$LOG"

# ─── Step 5: Backup Uploads ───
UPLOADS_BACKUP="no"
if [ -d "$UPLOADS_DIR" ] && [ "$(ls -A $UPLOADS_DIR 2>/dev/null)" ]; then
    tar czf "${BACKUP_FILE}_uploads.tar.gz" -C "$(dirname $UPLOADS_DIR)" "$(basename $UPLOADS_DIR)" 2>/dev/null
    /opt/homebrew/bin/gpg --yes --batch --recipient backup@leadvaults.io \
        --encrypt --output "${BACKUP_FILE}_uploads.tar.gz.gpg" "${BACKUP_FILE}_uploads.tar.gz" 2>/dev/null
    rm -f "${BACKUP_FILE}_uploads.tar.gz"
    UPLOADS_BACKUP="yes"
fi

# ─── Step 6: Local Retention (30 days) ───
ls -t "$BACKUP_DIR"/finance_*.db.gpg 2>/dev/null | tail -n +31 | xargs -r rm
ls -t "$BACKUP_DIR"/finance_*_uploads.tar.gz.gpg 2>/dev/null | tail -n +31 | xargs -r rm

# ─── Step 7: Remote Sync to Hetzner ───
REMOTE_OK="no"
if scp -q -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
    "${BACKUP_FILE}.db.gpg" "${REMOTE_HOST}:${REMOTE_DIR}/" 2>/dev/null; then
    REMOTE_OK="yes"
    # Clean remote backups older than 90 days
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$REMOTE_HOST" \
        "find $REMOTE_DIR -name 'finance_*.db.gpg' -mtime +90 -delete" 2>/dev/null || true
fi

if [ "$UPLOADS_BACKUP" = "yes" ]; then
    scp -q -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        "${BACKUP_FILE}_uploads.tar.gz.gpg" "${REMOTE_HOST}:${REMOTE_DIR}/" 2>/dev/null || true
fi

# ─── Step 8: Health Check ───
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:8000/ 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ App health: OK (200)" >> "$LOG"
    APP_OK="yes"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ App health: HTTP $HEALTH" >> "$LOG"
    APP_OK="no"
fi

# ─── Step 9: Verify GPG recovery keys on remote (weekly) ───
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" = "0" ]; then  # Sundays only
    KEY_CHECK=$(ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$REMOTE_HOST" \
        "ls $REMOTE_DIR/keys/gpg-backup-leadvaults.sec.asc.gpg 2>/dev/null" || echo "MISSING")
    if [ "$KEY_CHECK" = "MISSING" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ GPG recovery keys missing on remote" >> "$LOG"
    fi
fi

# ─── Step 10: Summary ───
BACKUP_SIZE=$(du -h "${BACKUP_FILE}.db.gpg" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Backup complete: ${BACKUP_SIZE} | Remote=${REMOTE_OK} | Health=${HEALTH}" >> "$LOG"

# Telegram notification
TG_STATUS="✅"
TG_MSG="${TG_STATUS} Lead Vaults Backup — ${BACKUP_SIZE}
• Integrity: OK
• Remote sync: ${REMOTE_OK}
• App health: ${HEALTH}
• Uploads: ${UPLOADS_BACKUP:-no}
• Rotated: 30d local, 90d remote"
tg_notify "$TG_MSG"

# ─── Rotate log ───
tail -50 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"

echo "✅ Backup complete — ${BACKUP_FILE}.db.gpg (${BACKUP_SIZE})"
