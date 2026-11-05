# 验证记录

最近更新：2026-11-04。

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
- `tests/test_event_contract.py` 与 `tests/test_events.py` 共 11 项测试通过，覆盖映射、创建、去重、筛选、状态转换、备注、证据字段、受保护证据图片路由、参数错误、持久化和 RDK 告警自动入库。
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

整合回归：60 项 unittest 全部通过，覆盖原有 51 项功能测试及新开关和规则回归；Edge 隔离账号验证管理员启停、普通用户只读，390px 布局无横向溢出、无 JS 错误。此处浏览器测试使用模拟画面和推理结果，不能替代实机准确率验收。

本机可选独立环境依赖检查通过；官方 yolov8n-pose.pt 经实际控制器完成合成空画面推理，状态进入 running、人数为零，关闭后进程退出。另覆盖网页服务异常退出时的管道监控，并避免 Windows 原生模型库初始化前启动阻塞读取线程。模型进程使用离线模式，避免启动时外网 DNS 探测。上述结果不代表实机分类准确率。

## 监控与事件 UX 改进（2026-11-04）

- 事件页新增 5 秒静默刷新、新事件提示、快捷筛选、5 分钟待处理超时提示、
  键盘导航和窄屏详情返回；刷新时保留筛选、排序和当前选中事件。
- 管理员与普通用户使用不同页面状态：普通用户隐藏整块备注和状态处置区，
  服务端继续执行管理员与 CSRF 校验。
- 监控首页的摔倒/斗殴红色告警增加“查看待处理事件”入口，并预置
  `status=pending&level=urgent&date=all&open=1` 查询参数。
- 统一事件契约新增 `evidence_url` 和 `evidence_captured_at`。证据 URL 只接受
  同源路径或 PNG/JPEG/WebP/GIF data URL，拒绝外部链接、协议相对路径和 SVG data URL。
- `tests/test_event_contract.py` 与 `tests/test_events.py` 共 11 项测试通过，
  新增覆盖证据字段的合法值、持久化及不安全 URL 拒绝。
- `tests/test_monitor_events_ux.py` 检查自动刷新、新事件提示、只读权限、告警跳转、
  证据与超时区域、快捷筛选、键盘操作、窄屏返回和 DOM ID 引用完整性。
- 事件页和监控页的内联 JavaScript 均通过 `node --check`；`git diff --check` 无空白错误。
- 本轮验证未连接新的 RDK 硬件，也未使用真实儿童证据图片。真实摄像头触发、
  证据文件产生、普通账号端到端只读和移动设备触控仍需在设备环境中验收。
## 红外测温实时对接（2026-11-04）

- `dashboard/health_realtime.py` 统一解析 `mlx_obj`、`mlx_amb`、设备编号、学生编号和
  ISO 8601/Unix 时间戳；`mlx_amb` 只作为环境温度，不进入学生体温字段。
- `GET /api/health/realtime` 每 2 秒由测温页读取，返回 `ready`、`unassigned`、
  `stale`、`timestamp_unknown`、`offline`、`invalid_temperature`、`unavailable`
  或 `unstable` 状态。
- `POST /api/health/device-readings` 支持设备令牌、新鲜度校验、学生匹配和 `reading_id`
  去重；只有有效、新鲜、稳定且关联到已知学生的读数才自动写入健康记录。
- `tests/test_health_realtime.py` 5 项测试覆盖字段归一化、无学生编号、过期、时间未知、
  非法温度、不稳定和设备离线；`tests/test_health_api.py` 新增设备令牌、自动入库、
  重复上报去重和实时接口测试。
- `dashboard/health-report.js` 已通过 `node --check`。
- 本轮使用模拟 RDK JSON 和隔离临时数据验证软件链路，未连接真实 MLX 红外传感器；
  实机温度偏差、画面目标定位、稳定帧判定和新旧设备字段差异仍需现场验收。

## 监控事件与实时红外整合（2026-11-04）

合并 PR #12 和 #13，并保留本地告警抓拍、会话删除和对话清空。完整 unittest 回归 82 项通过，覆盖抓拍权限、只读测温查询、设备令牌、未来时间拒绝和按设备去重。Edge 使用隔离账号和模拟 RDK 在 390px 宽度下验证抓拍加载、原图链接及读数填入测温表单。实际 RDK 和传感器仍待现场验证。

## 家长安全事件通知（2026-11-04）

- `event_contract.py` 新增 `participants` 和 `parent_visible_at`，摔倒要求
  1 名学生，斗殴要求至少 2 名学生，同名时必须用 `姓名@学号`。
- 事件页管理员处置区新增姓名录入；关联成功后家长事件接口只返回已关联且包含绑定
  孩子的事件。
- 家长账号新增 `parent` 角色和 `student_ids` 绑定，支持管理员创建及更新绑定；
  家长访问其他业务页面和 API 由服务端统一拒绝。
- 新增 `/api/family/events`、详情接口和受事件参与关系保护的截图接口；多人事件只
  返回当前家庭的孩子，内部备注和自由文本详情不会原样下发。
- 新增 `family-events.html` 家长事件箱，每 5 秒同步，展示事件状态、孩子、通用说明
  和授权截图。
- `tests/test_access.py`、`test_family_events.py`、`test_events.py` 和
  `test_monitor_events_ux.py` 覆盖角色绑定、未登录、越权、多人姓名过滤、截图越权、
  未关联事件隐藏、姓名解析和同名消歧。
- 自动化使用虚构学生和模拟告警，不包含真实儿童图片；RDK `/snapshot`、真实家长
  设备和新旧账号数据迁移仍需现场验收。

## 对话关注自动事件（2026-11-05）

- 情绪分析结果达到 `watch`/`urgent` 时自动创建 `dialogue_attention` 待处理事件，
  来源为 `dialogue`，事件详情只写通用说明与会话编号，不写入对话原文。
- 同一会话、同一等级在 `DIALOGUE_EVENT_WINDOW_SECONDS`（默认 600 秒）内只保留一条
  事件，避免连续表达刷屏；服务端重启后仍按 `dedupe_key` 去重。
- 分析线程未启动时（隔离测试或模型未配置）先用本地词库结果生成提醒；模型分析
  完成后按最终结果再次判断，不会重复创建。
- `tests/test_dialogue.py` 新增用例覆盖事件生成、去重和原文不落事件库；完整
  回归 104 项通过。

## 环境与设备异常自动事件（2026-11-05）

- Dashboard 启动后启动 `environment-monitor` 后台线程，默认每 30 秒读取
  `/api/iot_payload`，判断连接断开、采集时间缺失/过期、eCO₂ 和 TVOC 超限。
- 只在正常→异常的上升沿建事件，恢复后重置；同一异常按 1800 秒窗口用
  `dedupe_key` 去重，服务重启不会重复建事件。
- 阈值和周期均可用环境变量调整：`ENV_MONITOR_SECONDS`、`ENV_STALE_SECONDS`、
  `ENV_ECO2_LIMIT`、`ENV_TVOC_LIMIT`、`ENV_EVENT_WINDOW_SECONDS`；
  `ENV_MONITOR_ENABLED=0` 可关闭。
- 设备读取失败只写服务日志，不会因此生成“设备离线”事件，避免网络抖动刷屏。
- `tests/test_environment_events.py` 覆盖正常读数、离线边沿、恢复重置、过期数据、
  气体超限和缺失采集时间；完整回归 108 项通过。

## 事件播报与通知结果（2026-11-05）

- 新增可选播报通道：配置 `ALERT_NOTIFY_URL` 后，摔倒/斗殴事件保存时异步 POST
  JSON，供 ESP32 TTS 网关或其它服务播报；`ALERT_NOTIFY_TIMEOUT` 默认 3 秒，
  仅接受 http/https。
- 成功在事件处理记录追加“设备播报”，失败追加“设备播报失败”并记录异常类型；
  通知失败不阻断事件入库，未配置时不产生空记录。
- 网页端提醒仍由事件页轮询和新事件提示承担，不与设备播报耦合。
- `tests/test_events.py` 覆盖触发条件、成功记录和失败记录；完整回归 111 项通过。

## 抓拍状态与重新抓拍（2026-11-05）

- 事件新增 `snapshot_status`（`ok`/`failed`/`timeout`/`skipped`/空）和
  `snapshot_error`；自动抓拍失败或超时时写入原因并追加处理记录，页面显示
  “证据获取失败/超时”。
- 新增管理员重试接口 `POST /api/events/{id}/snapshot/retry`：重新读取 RDK
  `/snapshot`，成功显示证据，失败保留事件并记录原因；需要管理员会话和 CSRF。
- 事件页在失败状态显示“重新抓拍证据”按钮，成功后自动刷新证据区域。
- `tests/test_events.py` 覆盖自动成功、超时状态、重试成功和重试失败；完整回归 112 项通过。

## 工程规范整改（2026-11-05）

- 新增根目录 MIT `LICENSE`、`docs/SUPPLY_CHAIN.md`，补齐第三方版本、许可证与修改范围；
- 新增 `CONTRIBUTING.md`、`docs/CODE_STYLE.md`、`.editorconfig`、`pyproject.toml`、
  `.pre-commit-config.yaml`，提交前执行 ruff 与通用文件检查；
- 新增 Issue/PR 模板、`docs/GIT_WORKFLOW.md` 和 `docs/ISSUES_DRAFT.md`；
- CI 增加 ruff lint 任务，保留单元测试和仓库自检；
- 补充架构、设计模式、安全、测试计划、环境、配置、用户手册、团队 KPI、
  重构量化、实验设计和部署说明，并加入一键演示脚本 `scripts/demo.ps1`；
- 本地覆盖率测量：合计 80%（`server.py` 79%、`access_control.py` 91%、
  `event_contract.py` 88%），命令见 `docs/TEST_PLAN.md`；
- 当前完整回归：112 项测试通过，`verify_repository.py` 0 错误，ruff 0 错误。
