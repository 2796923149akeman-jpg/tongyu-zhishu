# Issue 草案（可直接在 GitHub 创建）

> 仓库没有自动化创建 Issue 的权限，以下内容可复制到 GitHub 新建 Issue 使用。
> 建议先建这 8 个，覆盖功能、修复、测试、文档和收尾任务。

## 1. 家长端：事件与日报权限隔离

**标签**：`type:feature` `area:family` `priority:high`

**内容**：家长账号只能查看绑定孩子的安全事件、日报和授权截图；多人事件只返回本人孩子，越权统一 404/403。已完成，补验收记录。

**验收**：`tests/test_family_events.py` 全绿；无痕窗口登录家长端只看到自己孩子。

## 2. 事件：老师按姓名关联参与学生

**标签**：`type:feature` `area:events` `priority:high`

**内容**：摔倒 1 人、斗殴至少 2 人，支持空格/全角逗号分隔、同名 `姓名@学号`；关联后家长可见。

**验收**：事件页操作成功；`tests/test_events.py` 覆盖重名与越权。

## 3. 环境与设备异常自动建事件

**标签**：`type:feature` `area:events` `priority:medium`

**内容**：后台每 30 秒读取传感器，连接断开、数据过期、eCO₂/TVOC 超限按上升沿建事件并去重。

**验收**：`tests/test_environment_events.py`；模拟 RDK 可复现。

## 4. 事件播报与抓拍失败重试

**标签**：`type:feature` `area:events` `priority:medium`

**内容**：`ALERT_NOTIFY_URL` 异步播报并记录成功/失败；抓拍失败记录 `snapshot_status`，管理员可重新抓拍。

**验收**：`tests/test_events.py` 通知与重试用例；页面显示失败原因。

## 5. 日报结构化 CSV 导出

**标签**：`type:feature` `area:reports` `priority:medium`

**内容**：日报页支持导出事件明细、关注对话、测温统计三张 CSV；保留打印/PDF。

**验收**：导出文件可用 Excel 打开，字段与页面一致；补接口/前端测试。

## 6. 维护日志与按编号查询

**标签**：`type:feature` `area:web` `priority:low`

**内容**：结构化运行日志（时间、模块、动作、结果、错误、事件/请求编号），提供按事件编号查询入口；日志脱敏。

**验收**：接口超时、抓拍失败、播报失败可在日志中查到；不记录 Cookie/密钥/原文。

## 7. 真实设备联调记录

**标签**：`type:test` `area:health` `priority:high`

**内容**：按 `docs/DEVICE_VALIDATION.md` 填写 ESP32、RDK X5、STM32、模型 API 的实测结果，附截图。

**验收**：记录表完整、结论明确；RDK `/snapshot` 抓拍链路已验证。

## 8. 演示视频与答辩材料

**标签**：`type:docs` `priority:high`

**内容**：按 `docs/DEMO_SCRIPT.md` 录制 7–9 分钟演示视频，更新 README 链接；准备答辩 PPT 和经验分享提纲。

**验收**：视频可播放、无真实儿童数据；README 有链接。

## 9. 测试与文档工作量记录

**标签**：`type:test` `type:docs` `priority:medium`

**内容**：测试同学维护 `docs/TEST_PLAN.md` 并在 Issue/PR 评论中记录执行结果；文档同学维护架构与用户手册，作为 KPI 依据。

**验收**：`docs/TEAM.md` 中能对应到 Issue/PR 记录。
