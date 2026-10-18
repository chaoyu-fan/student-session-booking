# GitHub → 服务器 Agent 交接

## 目前状态
连接的 GitHub 账号已经验证为 `chaoyu-fan`。目标仓库为 `chaoyu-fan/student-session-booking`，用户明确要求 **Public 开源**。服务器 Agent 应拉取 `main` 并在部署时记录 commit SHA。

## 发布仓库
- 开源地址：https://github.com/chaoyu-fan/student-session-booking （Public）。
- 仅发布源码、非敏感示例配置与部署文档；**绝不提交 `.env`、密码、数据库、备份与学生信息**。
- 服务器可匿名克隆 Public 仓库。升级时固定 Git commit，并先备份数据库、运行测试。

## Agent 接管后
- 首先读根目录 `AGENTS.md`、`README.md`、`docs/ACCEPTANCE.md`、`docs/PRIVACY.md`。
- 运行单元测试；不要跳过权限检查。
- 服务器运行脚本顺序 `init.sh → 编辑 .env → preflight.sh → deploy.sh → doctor.sh`。
- 审核脚本执行内容后再执行；当前脚本会启动/改动 Docker 容器，属于实际部署操作。
- 遇到已有站点占用 80/443，应停下报告，不得自动停止已有代理或应用。
- 完成后形成报告：Git SHA / 镜像 digest / 运行 URL / 健康检查 / 预约双重占用测试 / 备份恢复测试 / 风险与剩余人工工作。

## 需人工提供
- DNS 指向服务器的域名、所在时区、老师可预约日程、学校数据处理授权。
- 是否设置预约访问码及老师后台账号的安全交付方式。

## 前期误区纠正
- 不采用 Nextcloud Calendar 的公开预约，因为它当前默认依赖邮箱确认。
- 不强制任何社交平台身份登录。
- 不需要阿里云/腾讯云短信账号，也不需要微信小程序主体。
- 网站可通过学校允许的班级信息渠道分享链接；不应公开学生姓名及预约列表。
