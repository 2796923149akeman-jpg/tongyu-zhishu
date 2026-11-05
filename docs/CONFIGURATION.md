# 配置说明

更新日期：2026-11-05

所有配置通过环境变量注入，运行数据路径可覆盖；默认值集中在
`dashboard/server.py` 顶部。**不要修改源码中的默认值来适配本机**，应通过环境变量
或启动脚本设置。

## 1. 服务与访问

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DASHBOARD_HOST` | `127.0.0.1` | 直接运行 `dashboard/server.py` 的监听地址。F5 启动脚本固定使用回环地址 |
| `DASHBOARD_PORT` | `8088` | 网页与 API 端口 |
| `DASHBOARD_AUTH_FILE` | `dashboard/auth_config.json` | 账号与展示设置文件（已忽略） |
| `DASHBOARD_COOKIE_SECURE` | `1` | 会话 Cookie 是否加 `Secure`；仅本地 HTTP 演示可设 `0` |
| `RDK_BASE` | `http://192.168.43.54:5000` | 团队真机联调地址。换设备或网络时填写实际 RDK 服务 URL（含端口） |
| `PROJECT_ROOT` | 仓库根目录 | 小智配置与模型文件的根路径 |

## 2. 运行数据文件

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EVENTS_FILE` | `dashboard/events.json` | 事件库，最多 2000 条 |
| `EVIDENCE_DIR` | `dashboard/evidence/` | 旧版证据目录（可选） |
| `DIALOGUE_DATA_FILE` | `dashboard/dialogue_messages.json` | 对话消息，最多 200 条 |
| `DIALOGUE_CONFIG_FILE` | `dashboard/dialogue_config.json` | 对话页展示设置 |
| `CONVERSATION_SUMMARIES_FILE` | `dashboard/conversation_summaries.json` | 会话摘要 |
| `ANALYSIS_CONFIG_FILE` | `dashboard/analysis_config.json` | 情绪/摘要模型配置（含密钥，已忽略） |
| `EMOTION_LEXICON_FILE` | `dashboard/emotion_lexicon.json` | 本地情绪词库 |
| `HEALTH_STUDENTS_FILE` | `dashboard/health_students.json` | 学生名单 |
| `HEALTH_RECORDS_FILE` | `dashboard/health_records.json` | 体温记录 |

## 3. 环境与设备监控

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ENV_MONITOR_ENABLED` | `1` | 是否启动环境监控后台线程；`0` 关闭 |
| `ENV_MONITOR_SECONDS` | `30` | 读取传感器间隔（秒，最小 10） |
| `ENV_STALE_SECONDS` | `60` | 采集时间超过该值判定过期 |
| `ENV_ECO2_LIMIT` | `1000` | eCO₂ 告警阈值（ppm） |
| `ENV_TVOC_LIMIT` | `500` | TVOC 告警阈值（ppb） |
| `ENV_EVENT_WINDOW_SECONDS` | `1800` | 同类环境事件去重窗口 |
| `HEALTH_DEVICE_TOKEN` | 空 | 设备推送令牌，至少 24 位；为空时设备推送返回 503 |
| `HEALTH_INFRARED_STALE_SECONDS` | `10` | 红外读数新鲜度阈值 |

## 4. 对话与通知

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DIALOGUE_EVENT_WINDOW_SECONDS` | `600` | 同会话同等级情绪事件去重窗口 |
| `ALERT_NOTIFY_URL` | 空 | 播报网关地址，仅支持 http/https；为空时跳过播报 |
| `ALERT_NOTIFY_TIMEOUT` | `3` | 播报请求超时（秒） |

## 5. 示例

连接真机时，在启动 Dashboard 的同一个 PowerShell 窗口设置 `RDK_BASE`，将示例地址和端口换成该电脑能访问的 RDK 服务地址。环境变量优先于团队联调默认值。`scripts/demo.ps1 -NoMock` 同样需要先设置 `RDK_BASE`。

使用 `scripts/demo.ps1` 启动模拟演示时，脚本会为本次运行设置本机模拟 RDK 的地址（默认 `http://127.0.0.1:5000`）。

```powershell
$env:RDK_BASE = "http://<实际 RDK IP>:5000"
$env:ENV_ECO2_LIMIT = "1200"
$env:ALERT_NOTIFY_URL = "http://127.0.0.1:9000/alert"
$env:HEALTH_DEVICE_TOKEN = "<至少 24 位随机串>"
python scripts/run_dashboard.py
```

无硬件演示：

```powershell
python scripts/mock_rdk.py --port 5000
$env:RDK_BASE = "http://127.0.0.1:5000"
python scripts/run_dashboard.py
```

## 6. 原则

- 密钥、令牌只通过环境变量或本机被忽略的配置文件传入，不写进源码和文档；
- 阈值类配置有合理默认值，演示前按现场设备标定；
- 修改默认值会同时影响测试和演示，优先使用环境变量。
