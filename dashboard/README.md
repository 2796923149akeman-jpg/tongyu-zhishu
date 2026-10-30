# V1 基础监控看板

该版本完成电脑端对 RDK 真实数据的集中显示，并提供 ESP32 对话回顾、单句情绪线索和后台会话整理。

## 数据接口

- 画面：RDK `web_fall.py` 的 `/video_feed`
- 行为状态：RDK `web_fall.py` 的 `/alert_status`
- 温度和环境数据：RDK `web_fall.py` 的 `/api/iot_payload`

页面不生成模拟温度或空气质量数据；接口缺失的数值显示为 `--`，接口异常通过页面状态栏提示。

## 运行

手机演示、注册登录与管理员展示开关见 [手机演示指南](../docs/MOBILE_DEMO.md)。推荐在 VS Code 选择“启动网页服务”或“同时启动全部服务”，按 F5 自动打开统一登录页；首次创建一次管理员，以后复用账号和展示设置。需要手机外网链接时选择带“手机分享”的同名启动项。终端脚本 `scripts/start_mobile_demo.ps1` 仍可使用。当前默认只监听本机，所有业务页面和读取 API 均需登录。

配置上游数据接口地址后，在 Windows 终端运行：

```bat
cd /d D:\ESP32\tongyu-zhishu-v1
conda activate xiaozhi-esp32-server
set RDK_BASE=http://192.168.43.54:5000
python scripts/run_dashboard.py
```

浏览器打开 <http://127.0.0.1:8088>。

对话页为 <http://127.0.0.1:8088/chat>。登录后按权限查看；小智服务启动后，对 ESP32 说话即可查看识别文字、回复、情绪标签与需留意的会话；演示账号是否可读原文由管理员设置，最近 200 条记录保存在本机。

异常事件页为 <http://127.0.0.1:8088/events>。页面优先读取 `/api/events`，事件存储在本机运行时文件 `dashboard/events.json`（已被 Git 忽略，最多保留 2000 条）；状态处置和备注会写入服务器。RDK `/alert_status` 的 fall/fight 告警会自动写入事件，其他设备或人工登记可调用 `POST /api/events`，重复告警应提供稳定的 `dedupe_key`。接口不可用时页面明确回退到“演示数据”，不会把演示内容冒充真实记录。

学生测温页 <http://127.0.0.1:8088/health.html> 和日报页 <http://127.0.0.1:8088/reports.html> 已接入本机接口 `/api/health/*` 和 `/api/reports/daily`。学生与体温数据保存在被 Git 忽略的 `dashboard/health_students.json`、`dashboard/health_records.json`；日报事件通过 `event_for_report()` 使用统一等级/状态映射。默认班级为小二班、中一班、大一班，运行数据需要在本机导入或登记。

更新代码后需要重启 `python scripts/run_dashboard.py`；运行中的旧进程不会自动加载新增的 `/events` 路由。传感器数据需要提供采集时间 `timestamp`（带时区的 ISO 8601），页面才会按采集时间判断 20 秒过期；未提供时会显示“采集时间未知”，不会显示“数据正常”。

“模型与情绪设置”可控制：

- 直接修改小智服务当前对话模型的接口地址、模型名称和 API 密钥；
- 情绪分析使用对话模型，或完全离线的本地词库。

后台会话总结自动复用对话模型，但总结正文不在页面展示。对话模型保存在被 Git 忽略的 `xiaozhi-server/data/.config.yaml`，接口只返回“是否已设置”，不会返回密钥；修改后需重启小智服务才能用于新的实时对话。模型情绪分析会发送单句文本到所配置的服务，纯词库模式不会发送。情绪与留意标识只是文本线索，不是医学或心理诊断。

如果 RDK 地址变化，只修改 `RDK_BASE`，不需要修改代码。
