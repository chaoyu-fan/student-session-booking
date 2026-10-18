#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo '缺少 .env' >&2; exit 1; }
python3 - <<'PY'
import hashlib, pathlib, secrets, re
password=secrets.token_urlsafe(24)
salt=secrets.token_hex(10)
digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),1_000_000).hex()
p=pathlib.Path('.env')
s=re.sub(r'^ADMIN_PASSWORD_HASH=.*$', f"ADMIN_PASSWORD_HASH='pbkdf2:sha256:1000000${salt}${digest}'", p.read_text(), flags=re.M)
p.write_text(s)
q=pathlib.Path('secrets/admin-initial-password.txt')
q.parent.mkdir(parents=True,exist_ok=True)
q.write_text(password+'\n');q.chmod(0o600)
print('已更新本地密码哈希；凭据保存在 secrets/admin-initial-password.txt，需重启应用生效')
PY
docker compose up -d --force-recreate web
