# 验证记录

最近更新：2026-10-28。

- 7 项隔离自动化测试通过：监控/对话页面及 RDK JSON 代理路由、界面配置保存与校验、消息持久化、访问限制、重复消息和 200 条上限、生产 STT/TTS 入口到 HTTP 接收的顺序、转发故障不阻塞及恢复。
- 实际浏览器检查对话文字与用户/机器人标识，设备筛选生效，HTML 字样作为普通文本呈现；基础监控页的页面结构和接口错误展示符合预期。
- 本地运行依赖、FFmpeg、配置及模型文件清单检查通过。检查终端显式加入了现有 Conda 环境的 Library/bin 路径；日常启动需要先激活环境。
- 使用现有本机模型配置与儿童陪伴提示词发起一次独立的连通测试，DeepSeek `deepseek-chat` 成功返回文字。测试未使用真实儿童对话。
- 新增 GitHub Actions 配置，每次 push / pull request 运行隔离测试和待提交源码检查。
- 初始提交 `c499217` 已上传私人仓库，GitHub Actions 检查成功；远端文件清单确认不包含私有配置与模型。

自动化测试和浏览器预览使用隔离数据，不保存到实际运行目录。真实密钥和本地模型由 Git 忽略；初始提交前另行比对本机真实密钥，检查暂存清单。

## 监控页异常状态修复（2026-10-27）

- 同时出现 `alert_type=fall/fight` 和 `connected=false` 时，顶部保留红色紧急告警，并额外显示“传感器断开”标签；不再被灰色“设备离线”覆盖。
- 传感器页改为优先使用接口返回的采集时间 `timestamp` 判断是否超过 20 秒，不再把“刚刚收到响应”当作“刚刚采集”。
- 采集时间超过阈值显示“数据已过期”；未提供显示“数据时间未知 / 采集时间未知”；格式错误显示“采集时间异常”。三种情况都不会显示绿色“数据正常”。
- 页面兼容根节点或 `properties` 下的 `timestamp`、`ts`、`updated_at`、`collected_at` 等常见字段；推荐接口统一返回带时区的 ISO 8601 `timestamp`。
- `/events` 和 `/events.html` 路由测试通过。更新代码后必须重启 `python server.py`，旧进程不会加载新增页面路由。

浏览器检查截图：

- [摔倒告警与传感器断开同时出现](assets/monitor-fall-sensor-offline.png)
- [传感器采集时间为 1 小时前](assets/monitor-sensor-expired.png)
- [传感器接口未提供采集时间](assets/monitor-sensor-time-unknown.png)

检查覆盖 1440 px 桌面布局，并确认事件页在最新代码中可通过 `/events` 打开。真实硬件采集时间字段仍需在实际 `/api/iot_payload` 返回中确认。

## 异常事件接口（2026-10-28）

- 新增 `dashboard/event_contract.py`，统一事件字段、等级/状态枚举和 B/C 日报映射；`urgent/watch/info` 映射为日报的 `high/medium/low`，`resolved` 映射为 `handled`。
- 新增 `GET /api/events`、`GET /api/events/{id}`、`POST /api/events`、状态处置和备注接口，事件运行数据写入被 Git 忽略的 `dashboard/events.json`。
- 使用 `dedupe_key` 防止同一告警重复入库；默认最多保留 2000 条。
- `tests/test_event_contract.py` 与 `tests/test_events.py` 共 8 项测试通过，覆盖映射、创建、去重、筛选、状态转换、备注、参数错误、持久化和 RDK 告警自动入库。
- 事件页真实接口模式已通过本机 Dashboard 写入测试事件验证，页面显示绿色“接口数据”和真实事件；“接口不可用时回退到演示数据”的行为保留。

![事件接口真实模式](assets/monitor-events-live.png)

## 健康与日报接口（2026-10-28）

- 新增 `GET /api/health/students`、`GET /api/health/records`、`POST /api/health/records`、`POST /api/health/import` 和 `GET /api/reports/daily`；接口仅允许本机访问。
- 学生和体温记录分别持久化到被 Git 忽略的 `dashboard/health_students.json`、`dashboard/health_records.json`，默认班级为小二班、中一班、大一班。
- 日报通过 `event_for_report()` 将 `resolved` 映射为 `handled`，将 `urgent/watch/info` 映射为 `high/medium/low`；已处理事件不会进入待处理统计。
- `tests/test_health_api.py` 覆盖导入、重复跳过、体温范围、复测关系、筛选、日报班级过滤、事件映射和持久化；`tests/test_health_report.py` 6 项测试通过。
- 真实接口模式已通过导入 3 名学生、登记 3 条体温和写入 2 起事件的页面联调；学生测温页显示已测 2 / 未测 0 / 复测 1，日报显示 2 起事件、1 起已处置。
- 学生测温页和日报页增加跨天日期滚动：页面保持打开跨过午夜或从后台回到前台时，未手动选择历史日期的页面会自动切换到 Asia/Shanghai 的今天。

![学生测温真实接口](assets/health-page-live.png)

![日报真实接口](assets/reports-page-live.png)

## 疑似成人/儿童演示（2026-10-30）

- 新增 `dashboard/person_type.py`，用 YOLOv8 Pose 的头身比例和多帧投票输出 `adult/child/unknown`，只作为课堂演示估算。
- 新增 `scripts/person_type_demo.py`，支持电脑摄像头和 RDK `/video_feed`，结果写入被 Git 忽略的 `dashboard/person_types.json`。
- 初始演示分支通过 JSON 显示人数；2026-10-31 整合版改为默认关闭的实际进程开关、运行隔离及管理员控制。
- `tests/test_person_type.py` 3 项通过：比例规则、多帧投票/人数统计、缓存接口。
- 当前环境未连接实际摄像头，YOLOv8 Pose 推理和现场阈值仍需在实际 RDK 画面上校准。

## 先期设备联调记录

团队此前使用实际设备完成过接口联调，并确认以下数据能够传到服务端且按约定字段接收：

- RDK 的 `/video_feed` 视频流和 `/alert_status` 行为状态。
- STM32 经 `/api/iot_payload` 提供的连接状态、红外目标/环境温度、环境温湿度、eCO₂ 和 TVOC 数据。
- ESP32 到小智语音服务的 WebSocket 会话，以及用户识别文字和助手回复到 Dashboard 的消息链路。

这部分是团队提供的先期人工联调结论，作为 V1 网页开发的接口基线；本轮仓库自动化测试没有重新连接硬件复测。该结论只说明传输、接收和字段解析成功，不用于证明传感器测量精度、视觉算法准确率或所有网络环境的稳定性。

本记录验证本仓库内的网页和服务端软件。RDK 视觉识别、STM32 数据采集、ESP32 固件和机器人控制属于外部模块，不在本仓库隔离测试范围。全新电脑的依赖安装流程尚未单独复测。

对话页显示软件入口收到的消息并按句展示，最近 200 条消息保存在本机运行时文件中；网页服务未启动或发送队列已满时，对应消息不会进入记录。该记录用于课堂演示和运行查看，不构成完整的模型调用审计系统。

## 可选人物估算整合（2026-10-31）

保留现有登录、权限、F5 启动、跨日更新。新增管理员开关，默认关闭，停用实际终止进程；用同一 RDK 快照低频推理。修复未知帧投票、无跟踪编号跨人物历史、置信度缺失和旧文件被当作新结果的问题。自动化覆盖进程启停、权限、过期与运行编号隔离；真实儿童分类准确率与硬件延迟仍未验收。

整合回归：58 项 unittest 全部通过，覆盖原有 51 项功能测试及新开关和规则回归；Edge 隔离账号验证管理员启停、普通用户只读，390px 布局无横向溢出、无 JS 错误。此处浏览器测试使用模拟画面和推理结果，不能替代实机准确率验收。
