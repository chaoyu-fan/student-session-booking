#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups && chmod 700 backups
name="booking-$(date +%Y%m%d-%H%M%S).sqlite3"
docker compose exec -T -e BACKUP_NAME="$name" web python - <<'PY'
import os, sqlite3
source=sqlite3.connect('/data/booking.sqlite3')
target=sqlite3.connect('/data/'+os.environ['BACKUP_NAME'])
with target: source.backup(target)
target.close(); source.close()
print('SQLite 在线备份完成')
PY
docker compose cp "web:/data/$name" "./backups/$name"
docker compose exec -T -e BACKUP_NAME="$name" web python - <<'PY'
import os
os.unlink('/data/'+os.environ['BACKUP_NAME'])
PY
chmod 600 "./backups/$name"
echo "备份文件: backups/$name (请另行进行加密异地备份及恢复演练)"
