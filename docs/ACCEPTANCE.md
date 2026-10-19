# 部署与功能验收清单

以下测试**全部使用虚构学生姓名**。容器运行健康并不代表可以向真实学生开放。

## 自动化
- [ ] Python 单元测试 `python -m unittest discover -s tests -v` 全部通过。
- [ ] `docker compose config --quiet` 通过。
- [ ] `/healthz` 返回 HTTP 200。
- [ ] 管理后台未登录用户重定向登录页。
- [ ] CSRF 缺失的预约 POST 被拒绝。

## 人工端到端
- [ ] 微信内置浏览器与普通手机浏览器可正常使用完整中文页面。
- [ ] 学生能选择空闲日期、填写姓名，提交后立即显示成功，无邮箱确认。
- [ ] 同一开始时刻的两次并发提交只能成功一次。
- [ ] 后台插入与线上时段相交的临时会谈会被拒绝，反之亦然。
- [ ] 后台创建全天会议可使相应时间段从学生页面消失。
- [ ] 后台取消预约后该时段重新可预约；老师知道需手动联系原学生。
- [ ] 学生页面看不到其他学生的姓名、班级、预约详情。
- [ ] 前端不要求心理健康问题、联系电话或邮箱。
- [ ] 非授权人员无法访问老师后台，密码不在源代码或 GitHub。
- [ ] HTTPS 证书有效，HTTP 自动跳转 HTTPS，确认真实公网域名可用。
- [ ] 修改日程配置并重启后，新预约规则生效且旧数据仍保留。
- [ ] SQLite 备份成功并在隔离环境进行恢复演练。
- [ ] 学校许可数据存放地点、运营方与最小保留期限。

## 明确尚未提供的功能
- 学生自主认证（无账号模式无法证明身份）
- 自动取消/改期消息提醒
- 非工作日例外时间在线设置（目前配置文件中的每周规律 + 老师后台屏蔽）
- 真正日/周拖拽日历（目前是时间段选择 + 老师列表）
- 自动访问审计和高可用容灾

## Teacher's school timetable
- [ ] Before bell-time confirmation the public booking page displays no slots.
- [ ] Admin displays editable 8-period bell times and weekday × period class grid.
- [ ] Actual teacher timetable is entered privately in the admin/database, not the public repository.
- [ ] Students cannot book during recurring class hours including 10-minute buffers.
- [ ] Admin walk-in is refused when it overlaps a recurring class.
- [ ] Changing school times does not silently invalidate existing bookings.
- [ ] New database defaults match the eight exact periods in docs/SCHOOL-HOURS.md; periods 1–7 are 45m, period 8 is a **40m after-school service**.
- [ ] School-wide morning exercise 09:45–10:15 is independently blocked Mon–Fri even when the teacher has no class, and is configurable in admin.
- [ ] Importing the teacher's private weekly lesson JSON preserves the correct after-school lesson on Tuesday, period 8.
- [ ] Upgrading an unconfirmed reference timetable fills confirmed bell times; upgrading a previously activated customized schedule does not silently overwrite it.
- [ ] Teacher confirms pupils can actually attend sessions (teacher free alone is not sufficient).
