# 答辩演示视频录制脚本

更新日期：2026-11-05

已提交的 [42 秒模拟演示视频](https://github.com/2796923149akeman-jpg/tongyu-zhishu/releases/tag/course-demo) 使用模拟 RDK 和合成数据。
拥有仓库访问权限的评阅者可在 Release 的 Assets 区下载 `tongyu-course-demo.mp4`。

以下是 7–9 分钟的完整走查脚本，可用于彩排或后续录制。主流程为监控 → 告警 → 抓拍 → 处置 → 家长端 → 测温/日报 → 账号权限。
录屏前先读 [真实设备联调记录](DEVICE_VALIDATION.md)；没有硬件时用模拟 RDK
完成同等业务流程，并在视频中说明数据来源。

## 1. 录制准备

### 1.1 启动环境

```powershell
# 终端 1：模拟 RDK（无设备时使用；有设备则跳过并设置真实 RDK_BASE）
python scripts/mock_rdk.py --port 5000

# 终端 2：网页服务
$env:RDK_BASE = "http://127.0.0.1:5000"
$env:EVENTS_FILE = "dashboard/events.json"
python scripts/run_dashboard.py
```

首次启动按提示创建管理员；准备一个普通浏览器窗口（管理员）和一个无痕窗口
（家长账号），避免共享会话。

### 1.2 演示数据准备（提前做好，不录进视频）

1. 在「学生测温」导入 4–6 名学生（含班级），例如：
   ```text
   S-0201, 陈小满, 小二班
   S-0202, 王一诺, 小二班
   S-0203, 李一诺, 中一班
   ```
2. 在「账号管理」为 `chen-parent` 分配家长角色，绑定陈小满；为 `wang-parent`
   绑定王一诺；各开放事件、截图、日报权限（对话权限可只给一个演示）。
3. 在「展示设置」确认五个模块开放、摄像头画面开放。
4. 关闭无关窗口和通知；浏览器缩放 90%–100%；分辨率 1920×1080。

### 1.3 录屏工具

- Windows 自带 Xbox Game Bar（`Win+G`）或 OBS Studio；
- 只录浏览器窗口，隐藏书签栏；麦克风关闭，后期加字幕或旁白；
- 分段录制，出错可只重录某一段。

## 2. 分镜与操作

### 第 1 段（0:00–0:40）项目介绍

- 画面：登录页 + 一句字幕「童域智枢：多模态幼儿智能巡护系统」。
- 旁白：说明系统由监控、事件、对话、测温、日报、家长端组成，数据来自 RDK / STM32 / ESP32。

### 第 2 段（0:40–2:00）实时监控

- 操作：管理员登录 → 进入实时监控。
- 展示：视频画面、行为状态、六项读数、采集时间与过期/离线标识。
- 旁白：强调「异常提示不等于已处理」，引出统一事件流程。

### 第 3 段（2:00–4:00）摔倒告警与处置

1. 终端执行制造告警：
   ```powershell
   curl.exe -s -X POST http://127.0.0.1:5000/mock/alert -H "Content-Type: application/json" -d "{\"alert_type\":\"fall\"}"
   ```
2. 监控页出现红色告警 → 点击「查看待处理事件」。
3. 事件页：展示编号、时间、来源、抓拍证据、处理记录。
4. 点击「选择学生与截图权限」，选择陈小满，确认后展示参与学生与家长可见状态。
5. 管理员填写备注并「标记已处理」。

### 第 4 段（4:00–5:00）家长端

- 切到无痕窗口，用 `chen-parent` 登录 → 自动进入「家长工作台」。
- 展示：只出现陈小满的事件与截图；其他孩子事件不可见；日报按孩子隔离。
- 旁白：强调权限隔离、昵称显示和截图授权。

### 第 5 段（5:00–6:00）环境与对话异常

1. 终端制造环境异常：
   ```powershell
   curl.exe -s -X POST http://127.0.0.1:5000/mock/sensors -H "Content-Type: application/json" -d "{\"eco2\":1200,\"stale_seconds\":120}"
   ```
2. 事件页出现 `environment` / `sensor_expired` 事件（说明去重与阈值）。
3. 在对话页展示一条关注对话 → 事件页出现 `dialogue_attention` 事件，详情不含原文。

### 第 6 段（6:00–7:00）测温与日报

- 测温页：导入名单、实时红外读数、手动登记与复测、CSV 导出。
- 日报页：按日期/班级统计事件、关注对话、测温完成率与体温趋势，演示打印/PDF。

### 第 7 段（7:00–8:00）账号权限与收尾

- 展示账号管理：待分配账号 → 分配家长/商家/演示角色。
- 商家账号只能看环境传感器页；演示账号按展示开关访问。
- 收尾旁白：已知限制（真实设备联调、演示数据标识）与后续改进方向。

### 第 8 段（可选，8:00–8:30）播报与重试

- 配置 `ALERT_NOTIFY_URL` 后制造摔倒告警，事件处理记录出现「设备播报」或
  「设备播报失败」。
- 断开 `/snapshot` 制造抓拍失败，展示失败原因与「重新抓拍证据」。

## 3. 演示命令速查

```powershell
# 告警控制
curl.exe -s -X POST http://127.0.0.1:5000/mock/alert -H "Content-Type: application/json" -d "{\"alert_type\":\"fall\"}"
curl.exe -s -X POST http://127.0.0.1:5000/mock/alert -H "Content-Type: application/json" -d "{\"alert_type\":\"normal\"}"

# 传感器控制（值可组合）
curl.exe -s -X POST http://127.0.0.1:5000/mock/sensors -H "Content-Type: application/json" -d "{\"eco2\":1200,\"tvoc\":620}"
curl.exe -s -X POST http://127.0.0.1:5000/mock/sensors -H "Content-Type: application/json" -d "{\"connected\":false}"
curl.exe -s -X POST http://127.0.0.1:5000/mock/sensors -H "Content-Type: application/json" -d "{\"connected\":true,\"eco2\":520,\"tvoc\":60,\"stale_seconds\":0}"
```

## 4. 录制检查清单

- [ ] 不出现真实 API Key、真实儿童姓名照片或完整对话原文
- [ ] 演示数据页面有「演示数据」标识；模拟 RDK 在旁白中说明
- [ ] 每段操作有明确结果（事件出现、状态变化、家长端可见）
- [ ] 视频长度 7–9 分钟，字幕/旁白与画面一致
- [ ] 导出 1080p MP4，文件名 `童域智枢-演示-v{major}.mp4`
- [ ] 把视频链接或文件路径补到 [README](../README.md) 或答辩材料
