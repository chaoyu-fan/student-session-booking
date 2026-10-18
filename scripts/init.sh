#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -e .env ]]; then echo '已有 .env，拒绝覆盖现有密钥。' >&2; exit 1; fi
mkdir -p secrets backups
chmod 700 secrets backups
python3 - <<'PY'
import hashlib, secrets, pathlib, re
p=pathlib.Path('.env.example').read_text()
password=secrets.token_urlsafe(24)
salt=secrets.token_hex(10)
hashvalue=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),1_000_000).hex()
p=re.sub('^SESSION_SECRET=.*$',f'SESSION_SECRET={secrets.token_hex(32)}',p,flags=re.M)
p=re.sub('^ADMIN_PASSWORD_HASH=.*$',f"ADMIN_PASSWORD_HASH='pbkdf2:sha256:1000000${salt}${hashvalue}'",p,flags=re.M)
pathlib.Path('.env').write_text(p)
pathlib.Path('secrets/admin-initial-password.txt').write_text(password+'\n')
pathlib.Path('.env').chmod(0o600)
pathlib.Path('secrets/admin-initial-password.txt').chmod(0o600)
PY
echo '初始化完成。请编辑 .env 设置 BOOKING_DOMAIN，并从 secrets/admin-initial-password.txt 安全地查看管理员初始密码。'
