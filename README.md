# Student Session Booking | 学生会谈预约系统（开源中文版）

开源仓库：**https://github.com/chaoyu-fan/student-session-booking**。采用 MIT License。专门为**一位学校老师**和学生设计的预约网页。学生打开链接、选时间、填姓名、提交，**立刻预约成功**；没有邮箱、手机验证码、飞书或小程序资质要求。老师能查看预约、登记临时来访、屏蔽时间、取消预约。

**状态：可运行 MVP 源码与 Docker 部署配置；尚未在你的云服务器做端到端验收。** 请先用虚构学生信息测试；真正上线前由学校批准预约数据处理与存储方式。

## 功能
- 学生端：中文 H5 手机网页；未来 14 天空闲时段；50 分钟会谈、每小时开放一档；无需注册和邮件确认；确认页提示截图保存。
- 老师端：独立后台 `/admin`（初始用户为 `teacher`）；浏览未来 21 天日程；添加临时来访、会议/请假时段；取消日程。
- 预约规则：可预约基础窗口默认周一至周五 09:00–12:00、13:30–17:30，提前 3 小时；**先减去每周固定授课时间及前后各 10 分钟，再扣除已有预约/请假**。
- **学校课程表**：管理员在 `/admin` 填写周一至周五×1–8 节每周课程与八节铃声时间。演示作息时间仅供参考，首次必须经老师确认才能开放预约；老师课程表不提交进开源代码。
- 重复预约安全：SQLite `BEGIN IMMEDIATE` 数据库事务 + 时间重叠检测 + 唯一开始时间索引，阻止并发重叠预约。
- 默认不收集：手机号、邮箱、心理问题、病历、咨询记录。
- V1 没有：学生自助取消/改期、消息提醒、身份实名核验、老师端拖拽周历、学校统一登录。

> **特别注意**：因为不验证学生身份，网站无法保证姓名真实，也不能防止有人替别人预约。小范围内部试用可设置可选 `BOOKING_ACCESS_CODE`，但共享码也不是强实名验证。若发现恶意抢号，需增加验证码/校内身份验证。用户是未成年人不等于没有安全风险。

## 推荐服务器
Ubuntu 22.04 / 24.04、1–2 vCPU、至少 1–2GB RAM、Docker Engine 和 Compose v2、一个可用域名、可对外访问的 80/443 端口。Linux 公网域名 + Caddy 自动 HTTPS。

## 服务器 Agent 自动部署
```bash
# 拉取开源仓库
git clone https://github.com/chaoyu-fan/student-session-booking.git
cd student-session-booking
./scripts/init.sh      # 只执行一次；生成随机管理员凭据到本地 secrets/
vi .env                # 将 BOOKING_DOMAIN 改为真实已解析域名；检查学校时区与日程规则
./scripts/preflight.sh
./scripts/deploy.sh
./scripts/doctor.sh
```

访问 `https://<BOOKING_DOMAIN>/` 是学生端，`https://<BOOKING_DOMAIN>/admin` 是老师端。管理员初始用户名 `.env` 里 `ADMIN_USERNAME`，初始密码存放在服务器本地 `secrets/admin-initial-password.txt`（权限 600），不要在聊天、日志、截图公开密码。登录后台后可运行 `scripts/reset-admin-password.sh` 更换初始密码。

**不要执行** `docker compose down -v`，会删除业务数据卷。

如果服务器已经有 Nginx/Caddy 占用 80/443，`scripts/preflight.sh` 会拒绝新部署。应该让服务器 Agent **整合到现有反向代理**，而不是停掉正在运行的服务。可将 Compose `web` 绑定到本机 127.0.0.1 某端口并使用已有代理转发，但修改后需重新测试。

## 老师日常使用
1. 进入 `/admin` 登录，查看未来日程。
2. 学生临时来访：选择「学生临时来访」，填开始/结束时间、可选姓名及班级，保存后这个时段不会再开放线上预约。
3. 学校会议、休假：选择「会议 / 请假 / 不开放预约」添加占用时段。
4. 上线前先在后台「学校课程表」核对学校真实上下课时间并录入课表，点击「确认课表并开放预约」。没有确认前学生端不开放时段。
5. 取消预约：后台点击该日程的「取消」，再通过**学校既有渠道**通知受影响学生；V1 没有自动消息提醒。
6. 学生只需收到网站链接，可以微信扫码/微信群消息打开普通网页，**无需开发微信小程序**。

## 课程表与真实作息时间

本项目采用两层约束：**基础可约窗口 ∩ 老师没有课的时间 ∩ 未被其他日程占用的时间**。默认已将课程前后各 10 分钟纳入禁约范围，避免老师刚下课就需要开始长程会谈。老师空闲不代表学生能离开课堂，学校须自行确定学生可参与会谈的时段。

系统内置的八节课演示时间来自公开初中作息示例，但**绝不视为本校实际时间**。老师必须进入 `/admin` 调整八节起止时间、填写每周课程表并点击启用。没有确认之前，学生端显示“课表核对中”，不接受预约。

如果服务器 Agent 能从老师私下提供的真实课表生成 JSON，可以在服务器本地用 `scripts/import_local_timetable.py` 导入；**真实班级课表 JSON 不要提交到公开 GitHub 仓库**。课程表存储在 SQLite 数据卷中，随备份保存。已确认的学生预约如果与新课程时间冲突，系统拒绝新课程表覆盖，需老师先改期/取消既有预约。

## 服务器 Agent 本地导入实际课程表（可选）

后台同时支持**选择本地课表 JSON 文件直接导入**或手动编辑 40 个课程格。导入仅保存在服务器 SQLite，不公开至 GitHub。若要从照片转录并在服务器自动导入，可把**老师私下提供的 JSON 文件**上传到云服务器，不提交 GitHub。服务器 Docker 启动后：

```bash
# 假设老师本地课表位于服务器当前目录，文件不得上传 GitHub
chmod 600 teacher-timetable.private.json
docker compose cp teacher-timetable.private.json web:/tmp/teacher-timetable.private.json
# 先导入为草稿，不要加 --activate
# 容器的 /srv 中包含导入模块，DB_PATH 指向业务卷
docker compose exec -T web python -m scripts.import_local_timetable /tmp/teacher-timetable.private.json
# 老师登录 /admin 核对真实铃声时间，确认无误再启用
```

## 配置项
编辑服务器 `.env` 后，需要运行 `docker compose up -d --force-recreate web` 更新应用配置。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `BOOKING_DOMAIN` | `booking.example.com` | 必须改成真实域名 |
| `BOOKING_TIMEZONE` | `Asia/Shanghai` | 学校所在时区 |
| `SESSION_MINUTES` | `50` | 会谈时长 |
| `SLOT_MINUTES` | `60` | 每个可约时段之间的间隔 |
| `MIN_ADVANCE_HOURS` | `3` | 最晚提前多久预约 |
| `HORIZON_DAYS` | `14` | 开放未来多少天 |
| `BOOKING_ACCESS_CODE` | 空 | 可选访问码；请勿向无关人员公开 |
| `WORKDAYS` | `0,1,2,3,4` | 周一是 0，周日是 6 |
| `TEACHING_BUFFER_MINUTES` | `10` | 固定课程前后不可预约缓冲分钟数 |

## 代码和文档
- `AGENTS.md` — 服务器 Agent 的完整任务与不可执行操作
- `docs/AGENT-HANDOFF.md` — GitHub、服务器和部署交接流程
- `docs/ACCEPTANCE.md` — 功能验收清单
- `docs/PRIVACY.md` — 学校预约数据与未成年人保护
- `docs/OPERATIONS.md` — 备份、恢复演练、升级和监控
- `scripts/` — 初始化、预检查、部署、健康检查、SQLite 备份及密码重置
- `app/` — Flask + SQLite + 中文网页源码

## 本地开发和测试
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```
本地 HTTP 测试请在 **仅本机** 环境中配置 `COOKIE_SECURE=false`。此配置不可带到公网生产。

## V2（可选）
若学校师生都已使用飞书，再用飞书开放平台的自建应用实现校园认证和私聊提醒；创建应用、消息权限、可用范围及管理员审核仍需要学校支持。不要为了一个老师的预约功能在 V1 引入这些依赖。
