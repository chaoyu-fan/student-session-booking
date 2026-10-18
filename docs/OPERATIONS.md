# 日常维护与备份

## 日常检查
```bash
docker compose ps
docker compose logs --tail=100 web
./scripts/doctor.sh
```
请勿在共享日志中输出真实学生信息。

## 备份
```bash
./scripts/backup.sh
```
使用 SQLite 官方 `backup()` API 生成一致性在线备份，而不是直接 `cp` 运行中的 SQLite 文件。备份在本地 `backups/` 中（Git 忽略），**未加密且同机**；必须通过学校批准的加密介质/异地存储保存，适时清理，并演练恢复。

## 恢复演练（必须隔离）
在临时数据库运行：
```bash
python3 - <<'PY'
import sqlite3
src=sqlite3.connect('backups/你的备份文件.sqlite3')
print(src.execute('PRAGMA integrity_check').fetchone()[0])
print(src.execute('SELECT COUNT(*) FROM events').fetchone()[0])
src.close()
PY
```
实际故障恢复前必须有已确认的恢复目标、现存数据库的快照与授权。严禁自动覆盖生产数据。

## 更新
- 先备份并测试，再更新代码和镜像版本。
- 查看安全公告，审查依赖版本与运行日志；不要无测试自动滚动升级。
- 使用 `docker compose up -d --build` 部署修改。
- 严禁 `docker compose down -v` 或批量删除未知 Docker 卷。

## 域名及端口
默认 Caddy 监听 80/443。已有反向代理时停止默认部署，改成仅内网代理模式；不要擅自关闭已有业务。
