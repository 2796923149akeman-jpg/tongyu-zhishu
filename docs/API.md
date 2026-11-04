# Dashboard API 文档

默认服务地址为 `http://127.0.0.1:8088`。响应 JSON 使用 UTF-8，动态接口均返回 `Cache-Control: no-store`。

## 登录与权限

业务页面和读取 API 均需账号会话；按模块开关限制查看。除设备红外推送外，业务 POST 仅限管理员，必须同源并携带 `X-CSRF-Token`。`POST /api/health/device-readings` 使用独立的 `X-Device-Token`，不能读取名单或历史记录。`/api/auth/session` 提供 CSRF，注册账号固定为查看者，管理员通过本机初始化创建。`/health` 只返回 `{"ok": true}`，登录后用 `/api/config` 读取 RDK 地址。只有 `POST /api/dialogue/messages` 保留独立的本机机器上传检查，拒绝公网转发请求。完整流程见 [手机演示指南](MOBILE_DEMO.md)。

## 接口来源与验证说明

本文档同时区分两层地址：

- **设备侧上游接口**：RDK、STM32 和小智服务实际提供数据的地址，例如 RDK 的 `/video_feed`、`/alert_status` 和 `/api/iot_payload`。
- **V1 网页接口**：浏览器访问 Dashboard 的同源地址，例如 `/api/rdk/video_feed`、`/api/rdk/status`、`/api/rdk/sensors` 和 `/api/dialogue/messages`。

团队此前使用实际设备完成过联调，已确认：

1. RDK 视频流可以从 `/video_feed` 传到服务端并供网页显示。
2. 行为状态可以从 `/alert_status` 接收，`alert_type` 能够传递 `fall`、`fight` 及正常状态。
3. STM32 数据可以从 `/api/iot_payload` 接收，已使用的字段包括 `connected`、`properties.mlx_obj`、`mlx_amb`、`sht_t`、`sht_h`、`eco2` 和 `tvoc`。
4. ESP32 可以连接小智语音服务，对话中的用户识别文字与助手回复可以转发到 Dashboard。

上述联调确认的是传输链路、接收过程和字段解析，不是传感器测量精度或行为识别准确率测试。本仓库当前隔离测试通过模拟上游响应验证 V1 的代理和消息接口；硬件端程序、算法和实际测量精度不在该自动化测试范围内。

下文列出的路由均为当前已经实现的接口。异常事件、学生名单、测温记录和日报接口均已实现；日报使用事件统一契约做映射。

## 网页与服务状态

### `GET /`

返回基础监控页面。

### `GET /chat`

返回只读的对话记录页面。读取需登录并开放对话模块；配置写入仅限管理员。

### `GET /events`

返回异常事件页面。页面启动时读取 `GET /api/events`；接口不可用时，页面明确切换到带“演示数据”标识的样例，并在恢复后重新读取真实事件。
### `GET /health.html`

返回学生测温页面。页面优先读取本机健康接口；接口不可用时使用带“演示数据”标识的固定样例，字段约定见 [学生测温与当日日报](HEALTH_REPORT_UI.md)。

### `GET /reports.html`

返回当日日报页面，按日期和班级汇总安全事件处置、关注对话与测温完成情况。页面优先读取 `/api/reports/daily`；接口不可用时使用带标识的演示数据。

### `GET /health-report.css`、`GET /health-report.js`

上面两个页面共用的样式与脚本资源，随页面一起由 Dashboard 服务返回。

### `GET /health`

返回 Dashboard 服务状态和当前数据接口地址：

```json
{
  "ok": true,
  "rdk_base": "http://192.168.43.54:5000"
}
```

## 监控数据接口

### `GET /api/rdk/video_feed`

将上游 `/video_feed` 视频流转发给浏览器，响应类型沿用上游 `Content-Type`，通常为 `multipart/x-mixed-replace`。

### `GET /api/rdk/status`

请求上游 `/alert_status`，并将 JSON 原样返回。网页使用 `alert_type` 字段：

```json
{
  "alert_type": "fight"
}
```

页面识别 `fall` 和 `fight` 两个告警值，其他值按正常状态展示。

### `GET /api/rdk/sensors`

请求上游 `/api/iot_payload`，并将 JSON 原样返回。网页使用以下结构：

```json
{
  "timestamp": "2026-10-27T10:00:00+08:00",
  "connected": true,
  "properties": {
    "mlx_obj": 36.5,
    "mlx_amb": 25.8,
    "sht_t": 26.1,
    "sht_h": 55.0,
    "eco2": 420,
    "tvoc": 12
  }
}
```

`timestamp` 表示传感器采集时间，推荐放在根节点，也兼容 `properties.timestamp`、`ts`、`updated_at`、`collected_at` 等常见字段。时间必须是带时区的 ISO 8601（如 `2026-10-27T10:00:00+08:00`），也接受秒或毫秒时间戳。网页按采集时间判断传感器是否超过 20 秒未更新；如果接口没有提供采集时间或格式无法解析，页面会显示“采集时间未知/异常”，不会把数据标成“数据正常”。

上游请求超时、返回非 JSON 或网络异常时，Dashboard 返回 HTTP `502`：

```json
{
  "ok": false,
  "error": "RDK service unavailable",
  "detail": "错误信息",
  "rdk_base": "http://192.168.43.54:5000"
}
```

### `GET /api/rdk/person-types`

需登录并开放监控、视频权限（管理员不受开关限制）。返回可选人物估算进程状态；默认关闭，不启动模型。状态为 disabled、starting、running、stale 或 error。只有 running 返回本次运行且未过期的人数，不返回摄像头源地址、人物框、模型本地路径或日志。

```json
{"ok": true, "enabled": true, "state": "running", "estimate": true, "generated_at": "2026-10-31T10:00:00+00:00", "stale": false, "counts": {"adult": 1, "child": 2, "unknown": 0, "total": 3}}
```

### `POST /api/rdk/person-types/settings`

管理员同源请求，需 X-CSRF-Token，只接受严格布尔字段：

```json
{"enabled": true}
```

开启启动一个共享后台进程，画面源固定为当前 RDK_BASE 的 /snapshot。重复开启不重复启动。关闭会终止该进程；服务重启默认为关闭。缺少本地模型或依赖返回 400，页面提示准备环境。状态查询和控制均不调用远端模型服务，也不上传视频给外部分析服务。详见 [人物估算说明](PERSON_TYPE_DEMO.md)。

## 异常事件接口

事件读取需登录并开放事件模块；写入仅限管理员并验证 CSRF。统一字段和枚举定义在 `dashboard/event_contract.py`；事件页、日报和后续接口不得各自定义不同格式。

### `GET /api/events`

查询参数：

```text
status=pending|resolved|false_alarm
level=urgent|watch|info
source=rdk|sensor|dialogue|device|manual
class_id=C-02
student_id=S-0201
date_from=2026-10-28
date_to=2026-10-28
q=关键词
sort=newest|oldest
limit=50
offset=0
```

响应：

```json
{
  "ok": true,
  "events": [
    {
      "id": "EVT-20261028-ABC123",
      "event_type": "fall",
      "level": "urgent",
      "source": "rdk",
      "status": "pending",
      "occurred_at": "2026-10-28T09:42:10+08:00",
      "summary": "检测到疑似摔倒",
      "detail": "行为识别连续 3 帧返回 fall。",
      "device_id": "rdk-x5-01",
      "class_id": "C-02",
      "class_name": "小二班",
      "location": "活动室 A",
      "confidence": 0.86,
      "handled_at": null,
      "handled_by": null,
      "note": "",
      "dedupe_key": "rdk-fall-20261028-094210",
      "evidence_url": "/evidence/EVT-20261028-ABC123.png",
      "evidence_captured_at": "2026-10-28T09:42:10+08:00",
      "students": [
        {"id": "S-0201", "name": "陈小满"}
      ],
      "history": [
        {
          "at": "2026-10-28T09:42:10+08:00",
          "action": "系统检测",
          "by": "rdk",
          "note": "检测到疑似摔倒"
        }
      ],
      "updated_at": "2026-10-28T09:42:11+08:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0,
  "updated_at": "2026-10-28T09:42:11+08:00"
}
```

`evidence_url` 可选，只允许同源绝对路径（例如 `/evidence/event.png`）或
`data:image/png|jpeg|webp|gif;base64,...` 栅格图片；外部 URL、协议相对路径
和 SVG data URL 会被拒绝。`evidence_captured_at` 为可选的 ISO 8601 证据采集时间。
不要把真实儿童照片、可识别身份的画面或大体积 base64 数据提交到 Git。

证据文件可放在被 Git 忽略的 `dashboard/evidence/` 运行时目录，并通过受登录和
事件模块权限保护的 `GET /evidence/{文件名}` 读取。只允许
`.png`、`.jpg`、`.jpeg`、`.webp`、`.gif`，单文件最大 10 MiB；目录遍历和非图片
扩展名返回错误。证据采集程序负责写入文件，事件记录只保存同源路径。

### 告警自动截图

RDK `/alert_status` 从正常状态进入 `fall`/`fight` 并创建新事件后，Dashboard
会在后台从 `/video_feed` 抓取一帧 JPEG，写入
`dashboard/evidence/<事件编号>.jpg`，并把 `evidence_url` 与
`evidence_captured_at` 挂到事件上，处理记录追加“自动截图”。抓取或保存失败
不影响事件入库，事件保留空证据；同一告警持续期间不重复抓取，恢复正常后再次
告警才重新抓取。设置 `EVIDENCE_AUTO_CAPTURE=0` 可关闭自动截图，
`EVIDENCE_CAPTURE_TIMEOUT`（默认 6 秒）控制单次抓取的最长等待时间。

### `GET /api/events/{id}`

返回单个事件，响应为 `{"ok": true, "event": {...}}`。

### `POST /api/events`

写入一条事件。RDK `/alert_status` 的 fall/fight 会在监控代理轮询时自动入库；其他设备采集程序或人工登记入口调用：

```json
{
  "event_type": "fall",
  "level": "urgent",
  "source": "rdk",
  "occurred_at": "2026-10-28T09:42:10+08:00",
  "summary": "检测到疑似摔倒",
  "detail": "行为识别连续 3 帧返回 fall。",
  "device_id": "rdk-x5-01",
  "class_id": "C-02",
  "class_name": "小二班",
  "location": "活动室 A",
  "confidence": 0.86,
  "dedupe_key": "rdk-fall-20261028-094210"
}
```

成功返回 HTTP `201`。相同 `dedupe_key` 再次写入不会产生第二条事件，返回 HTTP `200` 和原事件，`duplicate` 为 `true`。

### `POST /api/events/{id}/status`

```json
{"status": "resolved", "note": "现场确认无受伤", "handled_by": "李老师"}
```

允许 `pending` → `resolved` / `false_alarm`，以及 `resolved` / `false_alarm` → `pending`（重新打开）。状态变更会追加 `history`。

### `POST /api/events/{id}/notes`

```json
{"note": "已通知现场老师", "author": "李老师"}
```

备注最多 200 字，会追加到 `history`。

### `POST /api/events/{id}/students`

老师在处理端确认事件涉及的儿童后，按姓名登记；多人用空格、全角空格、逗号或
顿号分隔：

```json
{"names": "陈小满 王一诺", "handled_by": "李老师"}
```

姓名必须与学生名单（`GET /api/health/students`）中的姓名完全一致；未找到或
同名无法唯一确认时返回 `400`，并在 `detail` 中列出无法确认的姓名。只有
`fall`/`fight` 事件可以关联学生。成功后事件增加：

```json
"students": [
  {"id": "S-0201", "name": "陈小满"},
  {"id": "S-0202", "name": "王一诺"}
]
```

处理记录追加“关联学生”。关联后，该事件会出现在对应家长的账号异常事件页中
（见“家长账号接口”）。重复登记会覆盖之前的关联结果。

### 统一枚举和日报映射

- `level`: `urgent` / `watch` / `info`
- `status`: `pending` / `resolved` / `false_alarm`
- 日报展示映射：`urgent→high`、`watch→medium`、`info→low`、`resolved→handled`
- 字段映射：`event_type→type`、`summary→title`、`handled_by→handler`

事件运行数据保存在被 Git 忽略的 `dashboard/events.json`，最多保留 2000 条。所有时间按 Asia/Shanghai 处理。

错误响应：

```json
{"ok": false, "error": "invalid event request", "detail": "invalid event_type"}
```

参数错误返回 `400`，事件不存在返回 `404`，非法状态转换返回 `409`，持久化失败返回 `500`。

## 学生名单、测温与日报接口

这些接口读取需登录并开放对应模块；写入仅限管理员并验证 CSRF。运行时数据写入被 Git 忽略的 `dashboard/health_students.json` 和 `dashboard/health_records.json`；默认提供 `C-02 小二班`、`C-11 中一班`、`C-21 大一班` 三个班级，学生需要导入或登记。

### `GET /api/health/students`

```json
{
  "ok": true,
  "students": [
    {"id": "S-0201", "name": "陈小满", "class_id": "C-02", "class_name": "小二班", "active": true}
  ],
  "classes": [
    {"id": "C-02", "name": "小二班"},
    {"id": "C-11", "name": "中一班"},
    {"id": "C-21", "name": "大一班"}
  ],
  "generated_at": "2026-10-28T09:00:00+08:00"
}
```

### `GET /api/health/records`

查询参数：`date=YYYY-MM-DD`（默认今天）、`class_id`、`student_id`。

```json
{
  "ok": true,
  "date": "2026-10-28",
  "records": [
    {
      "id": "R-ABC123",
      "student_id": "S-0201",
      "measured_at": "2026-10-28T09:12:31+08:00",
      "temperature_c": 36.6,
      "source": "forehead",
      "note": "",
      "recheck_of": null
    }
  ],
  "sources": [
    {"value": "forehead", "label": "额温枪"},
    {"value": "infrared", "label": "红外测温"},
    {"value": "ear", "label": "耳温枪"},
    {"value": "axillary", "label": "腋下体温计"}
  ]
}
```

### `GET /api/health/realtime`

需登录并开放健康模块。服务端请求 RDK `/api/iot_payload`，返回归一化后的最近红外读数、
采集时间、年龄、是否新鲜以及自动入库结果。`mlx_obj` 是目标温度，`mlx_amb` 仅作为环境
温度展示，两者不能混用。缺少采集时间或超过 `HEALTH_INFRARED_STALE_SECONDS`
（默认 10 秒）时返回 `stale` 或 `timestamp_unknown`，不会自动写入健康记录。

```json
{
  "ok": true,
  "source_available": true,
  "stale_after_seconds": 10,
  "reading": {
    "reading_id": "IRT-ABC123",
    "student_id": "S-0201",
    "device_id": "ir-01",
    "temperature_c": 36.6,
    "ambient_c": 24.8,
    "measured_at": "2026-11-04T10:20:08+08:00",
    "age_seconds": 2,
    "connected": true,
    "valid_temperature": true,
    "fresh": true,
    "status": "ready"
  },
  "ingest": {
    "stored": true,
    "duplicate": false,
    "reason": "stored",
    "record": {"id": "R-ABC123", "source": "infrared"}
  }
}
```

### `POST /api/health/device-readings`

供 RDK、STM32 或网关通过 `X-Device-Token` 推送红外读数。服务端要求环境变量
`HEALTH_DEVICE_TOKEN` 至少 24 位；请求不依赖浏览器管理员会话。

```json
{
  "connected": true,
  "stable": true,
  "student_id": "S-0201",
  "device_id": "ir-01",
  "reading_id": "IR-20261104-0001",
  "timestamp": "2026-11-04T10:20:08+08:00",
  "properties": {"mlx_obj": 36.6, "mlx_amb": 24.8}
}
```

只有读数有效、时间新鲜、`stable` 不为 `false` 且学生存在于名单时才自动入库。同一
`reading_id` 会去重。没有 `student_id` 时返回 `reason=unassigned`，页面仍显示实时值，
但不会猜测学生。成功入库返回 HTTP `201`，重复或仅展示返回 HTTP `200`。

### `POST /api/health/records`

```json
{
  "student_id": "S-0201",
  "temperature_c": 36.6,
  "source": "forehead",
  "note": "",
  "recheck_of": null
}
```

成功返回 HTTP `201` 和 `{"ok": true, "record": {...}}`。体温范围为 `35.0–42.0`，备注最多 50 字，来源必须为四种枚举之一；复测记录必须指向同一学生的原记录。

### `POST /api/health/import`

```json
{
  "students": [
    {"id": "S-0301", "name": "顾时安", "class_id": "C-02"}
  ]
}
```

返回 `{"ok": true, "imported": 1, "skipped": 0, "errors": []}`。已存在的学号计入 `skipped`；错误行包含 `line`、`reason` 和 `raw`。

### `GET /api/reports/daily`

查询参数：`date=YYYY-MM-DD`（默认今天）、`class_id`。

返回结构：

```json
{
  "ok": true,
  "report": {
    "date": "2026-10-28",
    "timezone": "Asia/Shanghai",
    "generated_at": "2026-10-28T20:00:00+08:00",
    "events": [
      {
        "id": "EVT-20261028-ABC123",
        "type": "fall",
        "title": "检测到疑似摔倒",
        "level": "high",
        "class_id": "C-02",
        "class_name": "小二班",
        "location": "活动室 A",
        "occurred_at": "2026-10-28T09:42:10+08:00",
        "status": "handled",
        "handler": "李老师",
        "handled_at": "2026-10-28T09:50:00+08:00",
        "note": "现场确认无受伤"
      }
    ],
    "dialogues": [],
    "health": {
      "total": 14,
      "measured": 9,
      "pending": 4,
      "recheck": 1,
      "classes": []
    }
  }
}
```

日报事件必须通过 `event_for_report()` 生成，不能直接复用事件库的 `resolved` 或 `urgent/watch/info` 枚举。日报健康状态使用 `measured/pending/recheck`；关注对话使用 `none/watch/urgent`。

`dialogues[]` 可选返回 `student_name`。如果消息源没有学生/班级映射，`student_id` 和 `class_id` 为空，页面显示“未关联学生”；按 `class_id` 查询日报时，空班级对话不会计入该班级。

## 对话消息接口

### `POST /api/dialogue/messages`

接收小智后端转发的单条消息。接口限服务电脑本机访问，请求头必须为 `Content-Type: application/json`，请求体不超过 64 KiB。

```json
{
  "id": "消息唯一编号",
  "role": "user",
  "text": "今天很开心",
  "device_id": "设备编号",
  "session_id": "会话编号",
  "created_at": "2026-10-17T10:00:00+00:00"
}
```

字段约束：

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | string | 必填，最多 64 字符；重复编号不会重复写入 |
| `role` | string | 只能为 `user` 或 `assistant` |
| `text` | string | 必填，最多 8192 字符 |
| `device_id` | string | 必填，最多 160 字符 |
| `session_id` | string | 必填，最多 160 字符 |
| `created_at` | string | 必填，最多 64 字符 |

成功返回：

```json
{"ok": true}
```

格式错误返回 HTTP `400`；非本机或跨站请求返回 HTTP `403`。

### `GET /api/dialogue/messages`

返回网页服务启动以来最近 200 条消息，按接收顺序排列：

```json
{
  "messages": [
    {
      "id": "消息唯一编号",
      "role": "assistant",
      "text": "真好呀，可以和我分享吗？",
      "device_id": "设备编号",
      "session_id": "会话编号",
      "created_at": "2026-10-17T10:00:01+00:00",
      "received_at": "2026-10-17T10:00:01.100000+00:00",
      "emotion": {
        "label": "happy",
        "label_text": "开心",
        "confidence": 0.86,
        "attention": "none",
        "source": "model+lexicon"
      }
    }
  ],
  "limit": 200
}
```

服务保留最近 200 条消息，并原子写入 `dashboard/dialogue_messages.json`。该运行时文件已由 Git 忽略；服务重启后会重新加载其中的记录。可通过环境变量 `DIALOGUE_DATA_FILE` 修改保存位置。

`emotion.source` 可能为模型结合词库、纯词库或模型失败后的词库兜底。`attention` 取值为 `none`、`watch`、`urgent`，只表示文本线索的查看优先级。

### `GET /api/dialogue/conversations`

按“优先查看、建议留意、普通”的顺序返回会话卡片数据，包括标题、后台摘要、主导情绪、留意原因、消息数量和更新时间。模型总结未生成或不可用时返回本地简要摘要；当前页面不展示摘要正文。

### `GET /api/dialogue/config`

返回对话界面的展示设置：

```json
{
  "config": {
    "title": "陪伴对话记录",
    "refresh_seconds": 2,
    "page_size": 50,
    "show_session_id": false,
    "show_created_at": true,
    "auto_scroll": true
  }
}
```

### `POST /api/dialogue/config`

保存完整的界面设置对象。标题为 1～40 个字符；刷新间隔可选 `1`、`2`、`3`、`5`、`10` 秒；显示数量可选 `20`、`50`、`100`、`200`。三个显示开关必须为布尔值。配置使用原子写入保存到被 Git 忽略的 `dashboard/dialogue_config.json`，也可通过环境变量 `DIALOGUE_CONFIG_FILE` 修改位置。

示例默认值见 `dashboard/dialogue_config.example.json`。请求格式错误返回 HTTP `400`，保存失败返回 HTTP `500`。

### `GET /api/dialogue/model`

返回小智服务当前对话模型的模块名、接口地址、模型名称和密钥是否已设置。接口不会返回 API 密钥原文。

### `POST /api/dialogue/model`

直接更新 `xiaozhi-server/data/.config.yaml` 中当前选中的 LLM。请求字段为 `base_url`、`model_name` 和 `api_key`；密钥留空会保留原值。公网接口只接受 HTTPS，本机 `localhost`、`127.0.0.1` 或 `::1` 可使用 HTTP。保存后需重启小智服务，新的实时对话才会使用新模型。

## 智能分析接口

### `GET /api/analysis/config`

返回后台分析配置。页面只使用其中的情绪分析方式；对话总结固定在后台启用并复用小智对话模型。

### `POST /api/analysis/config`

保存智能分析设置。当前页面只允许情绪模式选择 `model_fallback`（对话模型分析，失败时词库兜底）或 `lexicon`（仅本地词库）。服务端会固定启用后台会话总结，并让总结和模型情绪分析共同复用小智对话模型。

### `POST /api/analysis/rebuild`

请求体为 `{}`，返回 HTTP `202`，把现有消息的情绪分析和会话总结加入后台队列。后台分析不阻塞 ESP32 消息接收和语音链路。

以上模型和分析设置接口仅限管理员同源访问，写操作需 CSRF。

## 通用错误

不存在的路径返回 HTTP `404`：

```json
{
  "ok": false,
  "error": "not found"
}
```
