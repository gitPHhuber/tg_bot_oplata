#!/usr/bin/env bash
# Ежедневный бэкап БД бота и БД 3x-ui панели.
# Настроить через cron:  0 4 * * *  /opt/vpn-bot/deploy/backup.sh
set -euo pipefail

BACKUP_DIR="/root/backups"
KEEP_DAYS=14
TS=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

# Бот: БД через .backup (consistent даже при WAL)
if [ -f /opt/vpn-bot/data/bot.db ]; then
  sqlite3 /opt/vpn-bot/data/bot.db ".backup '$BACKUP_DIR/bot-$TS.db'"
fi

# 3x-ui: dump SQLite базы панели
if [ -f /etc/x-ui/x-ui.db ]; then
  sqlite3 /etc/x-ui/x-ui.db ".backup '$BACKUP_DIR/xui-$TS.db'"
fi

# Hysteria2 config — yaml, просто копия
if [ -f /etc/hysteria/config.yaml ]; then
  cp /etc/hysteria/config.yaml "$BACKUP_DIR/hysteria-$TS.yaml"
fi

# Удаляем старое
find "$BACKUP_DIR" -type f -mtime +$KEEP_DAYS -delete

echo "[$(date)] backup ok → $BACKUP_DIR"
