# Dashboard API 文档

默认服务地址为 `http://127.0.0.1:8088`。响应 JSON 使用 UTF-8，动态接口均返回 `Cache-Control: no-store`。

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

下文列出的路由均为 V1 当前已经实现的接口。异常事件、学生名单、测温记录和日报等后续接口，只有在实现、测试并补充到本文档后才属于正式接口。

## 网页与服务状态

### `GET /`

返回基础监控页面。

### `GET /chat`

返回只读的对话记录页面。此页面、消息接口和界面配置接口只允许从服务电脑的 `localhost`、`127.0.0.1` 或 `::1` 访问。

### `GET /health.html`

返回学生测温页面。页面本身只提供静态结构和交互逻辑，名单、测温记录与日报数据需要后续接口；接口未实现时页面使用带“演示数据”标识的固定样例，字段约定见 [学生测温与当日日报](HEALTH_REPORT_UI.md)。

### `GET /reports.html`

返回当日日报页面，按日期和班级汇总安全事件处置、关注对话与测温完成情况。当前同样使用带标识的演示数据。

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

上游请求超时、返回非 JSON 或网络异常时，Dashboard 返回 HTTP `502`：

```json
{
  "ok": false,
  "error": "RDK service unavailable",
  "detail": "错误信息",
  "rdk_base": "http://192.168.43.54:5000"
}
```

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

以上接口与对话页面一样，仅允许服务电脑本机同源访问。

## 通用错误

不存在的路径返回 HTTP `404`：

```json
{
  "ok": false,
  "error": "not found"
}
```
