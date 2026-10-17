# Dashboard API 文档

默认服务地址为 `http://127.0.0.1:8088`。响应 JSON 使用 UTF-8，动态接口均返回 `Cache-Control: no-store`。

## 网页与服务状态

### `GET /`

返回基础监控页面。

### `GET /chat`

返回对话测试页面。此页面及其消息读取接口只允许从服务电脑的 `localhost`、`127.0.0.1` 或 `::1` 访问。

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
      "received_at": "2026-10-17T10:00:01.100000+00:00"
    }
  ],
  "limit": 200
}
```

消息仅保存在内存中，网页服务重启后清空。

## 通用错误

不存在的路径返回 HTTP `404`：

```json
{
  "ok": false,
  "error": "not found"
}
```
