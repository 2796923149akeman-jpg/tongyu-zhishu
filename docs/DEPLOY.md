# 部署与运行说明

更新日期：2026-11-05

## 1. 环境要求

| 组件 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（演示机）；Linux 亦可运行 |
| Python | 3.10 及以上 |
| 依赖 | `pip install -r tests\requirements.txt`（含网页与测试依赖） |
| 浏览器 | Edge / Chrome 最新稳定版 |
| 设备（可选） | RDK X5、STM32 传感器、ESP32；无设备时用模拟 RDK |

## 2. 一键演示（无硬件）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
```

脚本会启动模拟 RDK、设置 `RDK_BASE`、启动 Dashboard 并打开登录页。
按 Ctrl+C 停止，脚本会一并关闭模拟服务。
首次运行需要在终端初始化管理员。自动验证可加 `-NoBrowser`，并用
`-MockPort` 和 `-DashboardPort` 指定两个不同的本机端口。

手动方式：

```powershell
python scripts/mock_rdk.py --port 5000
$env:RDK_BASE = "http://127.0.0.1:5000"
python scripts/run_dashboard.py
```

## 3. 连接真实设备

```powershell
$env:RDK_BASE = "http://<RDK实际IP>:5000"
$env:HEALTH_DEVICE_TOKEN = "<至少 24 位随机串>"
python scripts/run_dashboard.py
```

1. RDK 端启动 `web_fall.py`，确认 `/alert_status`、`/api/iot_payload`、`/snapshot` 可访问；
2. ESP32 指向 `ws://<电脑IP>:8000/xiaozhi/v1/`，OTA 为 `8003`；
3. 首次运行在终端创建管理员，再打开 <http://127.0.0.1:8088/login> 登录并导入名单。

`run_dashboard.py` 的网页监听固定为本机回环地址。手机访问使用 [手机分享说明](MOBILE_DEMO.md) 中的 `--share`。
`DASHBOARD_HOST` 只影响直接运行 `dashboard/server.py` 时的监听地址。

## 4. 配置项

完整变量见 [配置说明](CONFIGURATION.md)。常用：

| 变量 | 说明 |
|---|---|
| `RDK_BASE` | RDK 地址 |
| `DASHBOARD_HOST` / `DASHBOARD_PORT` | 监听地址与端口 |
| `HEALTH_DEVICE_TOKEN` | 设备推送令牌 |
| `ALERT_NOTIFY_URL` | 播报网关（可选） |
| `ENV_ECO2_LIMIT` / `ENV_TVOC_LIMIT` | 环境阈值 |

## 5. CI 与检查

```powershell
python -m unittest discover -s tests -v
python scripts/verify_repository.py
ruff check dashboard scripts tests
```

GitHub Actions 在 push/PR 时执行同样检查，见 `.github/workflows/checks.yml`。

## 6. 部署注意事项

- 公网演示通过 cloudflared 等 HTTPS 隧道，保持 `DASHBOARD_COOKIE_SECURE=1`；
- 不要暴露 RDK 5000、小智 8000/8003 到公网；
- 运行数据、抓拍、账号文件只保存在本机，已被 `.gitignore` 排除；
- 演示结束清理真实名单、对话和抓拍，或使用模拟数据；
- 更多安全建议见 [安全设计](SECURITY.md)。

## 7. 常见问题

| 现象 | 处理 |
|---|---|
| 端口被占用 | 修改 `DASHBOARD_PORT` 或停止旧进程 |
| 页面提示 RDK 不可用 | 检查 `RDK_BASE`、网络和 RDK 进程 |
| 视频不显示 | 管理员开放摄像头；确认 `/video_feed` |
| 抓拍失败 | 确认 RDK `/snapshot`；事件页可重试 |
| 设备推送 503 | 配置 `HEALTH_DEVICE_TOKEN`（≥24 位） |
| Python 找不到依赖 | 使用 `.venv` 解释器并安装 `tests/requirements.txt` |
