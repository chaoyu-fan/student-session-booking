#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo '缺少 .env' >&2; exit 1; }
docker compose ps
docker compose exec -T web python - <<'PY'
import urllib.request
r=urllib.request.urlopen('http://localhost:8000/healthz',timeout=5)
assert r.status == 200
print('应用及 SQLite 健康检查通过')
PY
python3 - <<'PY'
from pathlib import Path
for line in Path('.env').read_text().splitlines():
    if line.startswith('BOOKING_DOMAIN='):
        domain=line.split('=',1)[1]
        print(f'请浏览器验证 https://{domain}/ 学生端和 /admin 老师端；此检查不会证明 DNS/TLS 已生效。')
        break
PY
