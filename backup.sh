#!/bin/bash
# Family Finance backup script
# Safe hot backup using sqlite3 .backup command
# Copies to Hetzner server

set -e

BACKUP_DIR="/Users/suren/family-finance/backups"
DB_PATH="/Users/suren/family-finance/data/finance.db"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/finance_$TIMESTAMP.db"
REMOTE_DIR="/root/finance-backups"
REMOTE_HOST="root@62.238.12.115"

mkdir -p "$BACKUP_DIR"

# Safe hot backup (consistent snapshot, doesn't block writers)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Compress
gzip -f "$BACKUP_FILE"

# Keep last 30 local backups
ls -t "$BACKUP_DIR"/finance_*.db.gz 2>/dev/null | tail -n +31 | xargs -r rm

# Sync to Hetzner (keeps last 90 days there)
scp -q "${BACKUP_FILE}.gz" "${REMOTE_HOST}:${REMOTE_DIR}/"

# Cleanup old remote backups (older than 90 days)
ssh "$REMOTE_HOST" "find $REMOTE_DIR -name 'finance_*.db.gz' -mtime +90 -delete" 2>/dev/null

echo "Backup complete: ${BACKUP_FILE}.gz"
