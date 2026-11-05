# 实验环境说明

更新日期：2026-11-05

## 1. 开发与演示环境

| 项目 | 配置 |
|---|---|
| 操作系统 | Windows 11（开发机）；GitHub Actions 使用 Ubuntu Latest |
| Python | 开发机 3.10 / 3.12；CI 固定 3.10 |
| 网页依赖 | Python 标准库 + `PyYAML==6.0.3`（`dashboard/requirements.txt`） |
| 测试依赖 | `httpx==0.28.1` + 网页依赖（`tests/requirements.txt`） |
| 浏览器 | Microsoft Edge / Chrome 最新稳定版；移动端按 390–504 px 宽度检查 |
| 语音服务 | 小智 Python 后端（Python 3.10、FFmpeg、libopus），模型见 `docs/model-files.json` |
| 人物估算（可选） | Ultralytics / PyTorch / OpenCV，默认关闭 |

## 2. 硬件与网络

| 设备 | 用途 | 连接方式 |
|---|---|---|
| RDK X5 | 摄像头视频、行为识别、红外与环境传感器、`/snapshot` | HTTP `http://<RDK_IP>:5000` |
| STM32 / 传感器 | 体温、温湿度、eCO₂、TVOC | 由 RDK 汇总到 `/api/iot_payload`，或设备令牌推送 |
| ESP32 | 语音输入输出 | WebSocket `ws://<电脑IP>:8000/xiaozhi/v1/`，OTA `8003` |
| 演示电脑 | Dashboard、小智后端 | 与设备同一局域网；默认端口 `8088` |

- 开发机与 RDK 需网络互通；跨网段时使用可路由地址或热点。
- 手机分享使用 cloudflared 临时 HTTPS 链接（可选），见 `docs/MOBILE_DEMO.md`。
- 演示前记录实际 IP、端口、网络环境，填入 `docs/DEVICE_VALIDATION.md`。

## 3. 端口

| 端口 | 服务 |
|---|---|
| 8088 | Dashboard 网页与 API |
| 8000 | 小智 WebSocket |
| 8003 | 小智 OTA / HTTP |
| 5000 | RDK 数据接口（默认） |

## 4. 测试环境

- 自动化测试使用隔离的临时目录和模拟上游响应，不依赖真实设备或付费 API；
- 单元测试通过 `unittest discover` 运行，CI 在 Python 3.10 上执行；
- 浏览器检查为手工/静态检查，说明见 `docs/VALIDATION.md`；
- 真实设备联调结果单独记录，不与模拟测试混为一谈。

## 5. 环境变量

完整配置项与默认值见 [配置说明](CONFIGURATION.md)。演示常用：

```powershell
$env:RDK_BASE = "http://192.168.43.54:5000"
$env:DASHBOARD_HOST = "0.0.0.0"
$env:HEALTH_DEVICE_TOKEN = "<至少 24 位随机串>"
```

## 6. 已知环境限制

- Windows 下 shell 命令以 PowerShell 为准；CMD 写法见 `docs/MOBILE_DEMO.md`。
- 浏览器时间显示统一 `Asia/Shanghai`，服务器时区不同也不影响展示。
- 未配置 `HEALTH_DEVICE_TOKEN` 时，设备推送接口返回 503，属于预期行为。
- 没有真实设备时使用 `scripts/mock_rdk.py`，模拟数据会明确标注。
