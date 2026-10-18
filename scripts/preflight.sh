#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo '缺少 Docker' >&2; exit 1; }
docker compose version >/dev/null || { echo '缺少 Docker Compose v2' >&2; exit 1; }
docker info >/dev/null || { echo 'Docker daemon 不可访问' >&2; exit 1; }
[[ -f .env ]] || { echo '先运行 ./scripts/init.sh' >&2; exit 1; }
python3 - <<'PY'
from pathlib import Path
import re, sys
text=Path('.env').read_text()
vals=dict(line.split('=',1) for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#') and '=' in line)
domain=vals.get('BOOKING_DOMAIN','')
if domain=='booking.example.com' or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{2,252}',domain) or '.' not in domain:
    sys.exit('BOOKING_DOMAIN 未设置为有效的真实域名')
if len(vals.get('SESSION_SECRET',''))<40 or 'replace-' in vals.get('ADMIN_PASSWORD_HASH',''):
    sys.exit('密钥未完成初始化')
if not 15<=int(vals.get('SESSION_MINUTES','50'))<=180: sys.exit('SESSION_MINUTES 不合规')
if int(vals.get('SLOT_MINUTES','60'))<int(vals.get('SESSION_MINUTES','50')): sys.exit('SLOT_MINUTES 必须 >= SESSION_MINUTES')
print('环境变量检查通过，目标域名:',domain)
PY
docker compose config --quiet
printf 'Compose 格式检查通过。\n'
if [[ -z "$(docker compose ps -q caddy 2>/dev/null)" ]] && command -v ss >/dev/null; then
  if ss -ltn | grep -Eq '(:80|:443)[[:space:]]'; then
    echo '服务器已有进程监听 80/443，请检查端口占用后再部署（不能擅自停止已有服务）。' >&2
    exit 1
  fi
fi
printf '前置检查通过。请另行确认 DNS、HTTPS、学校授权及磁盘备份规划。\n'
