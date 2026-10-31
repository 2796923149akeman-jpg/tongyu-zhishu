# 童域智枢：网页监控与语音交互软件

## 1. 项目简介

本仓库是“童域智枢”项目的网页可视化与语音交互软件，负责监控信息展示、行为状态提示、环境数据展示和对话消息查看。设备通信与数据字段沿用团队先期联调确认过的接口，网页的信息架构、布局、样式和交互在本课程仓库中独立设计和实现。

### 项目边界与依赖关系

本仓库负责网页展示、设备数据接口接入及语音交互服务集成。RDK 视觉识别、STM32 传感器采集、ESP32 设备固件和机器人运动控制由独立模块实现；它们通过约定接口向本软件提供数据，不属于本仓库的源码范围，也不作为本仓库的软件实现内容。

### 开发基线与验证边界

团队在先期实际设备联调中已确认以下传输链路能够工作：

- RDK 的视频流与行为状态能够传到 Dashboard。
- STM32 的体温、环境温湿度、eCO₂ 和 TVOC 字段能够被服务端接收和解析。
- ESP32 能够连接小智语音服务，对话文字能够转发到 Dashboard。

这里的“已确认”是指设备传输、服务端接收和字段解析曾完成联调，不代表本仓库的隔离测试重新测量了传感器精度，也不代表所有网络环境下都不会出现连接问题。V1 自动化测试使用隔离的上游响应检查网页路由、字段处理、访问限制和消息持久化；实际设备联调结果作为本次网页开发的接口基线。详细说明见 [API 文档](docs/API.md) 和 [验证记录](docs/VALIDATION.md)。

本地目录 `tongyu-zhishu-v1` 是上述 GitHub 课程仓库在开发电脑上的工作副本。Git 的远端地址只决定从哪里拉取、向哪里推送，不能说明代码或设计思路来自哪里；项目来源与复用范围应以本节、提交历史和第三方来源说明为准。

## 2. 功能概览

- 监控画面：在浏览器中展示上游视频流。
- 行为提示：展示正常、摔倒和斗殴等识别状态。
- 可选人物估算（实验）：监控页由管理员开关，默认关闭；开启运行姿态比例估算，关闭停止进程，普通用户只读。需单独准备依赖和本地模型，见 [人物估算说明](docs/PERSON_TYPE_DEMO.md)。
- 环境数据：展示体温、环境温湿度、eCO₂ 和 TVOC。
- 注册登录：普通用户自行注册；管理员由运行电脑上的首次启动流程创建。同一登录页根据账号角色分配入口，无需手选身份。
- 展示权限：管理员控制五个模块、摄像头画面和对话原文开关。普通用户只读，所有普通账号共用一套展示配置；管理员可查看和管理全部模块。
- 对话记录：持久化保存最近 200 条用户识别文字和机器人回复；左侧按北京时间的日期、设备、会话选择，支持关键词搜索，机器人在左、用户在右。查看历史会话时刷新保留选择。
- 对话与模型设置：管理员可设置标题、刷新间隔、显示数量，以及对话模型、单句情绪分析方式；支持本地词库和模型分析失败回退。
- 异常事件：真实事件保存、筛选、详情、处置状态及备注；RDK 行为状态被读取时，新增的摔倒/斗殴告警可写入事件库。
- 学生测温：管理员导入学生名单、手动登记体温及复测，数据保存在运行电脑中。设备体温自动关联学生尚未实现。
- 当日日报：汇总事件、需留意的对话和测温状态；受模块及原文权限控制。测温与日报查看当天时跨日自动切到新一天，主动选择的历史日期保留。
- 一键启动与手机分享：VS Code F5 启动网页或同时启动小智服务，自动打开登录页；可选 cloudflared 生成临时 HTTPS 手机链接。

账号、密码哈希与展示开关保存在本机，重启无需重新注册；重启服务后需重新登录。默认开放五个模块，视频和对话原文默认关闭，管理员不受限制。没有预设的通用管理员用户名或密码，网页注册的账号始终是普通用户。

当前边界：不支持为每个普通账号单独分配模块，也没有找回密码或账号管理页面。设备采集时间偏差、环境数据过期原因和真实手机公网可达性仍需现场验证；首页地址显示修复不等于设备时钟已校准。

## 3. 系统软件架构

```mermaid
flowchart LR
    Browser[浏览器] -->|HTTP| Dashboard[Dashboard 网页服务]
    RDK[RDK 数据接口] -->|视频流 / 状态 / 环境数据| Dashboard
    Xiaozhi[小智语音后端] -->|对话消息 HTTP| Dashboard
    Dashboard --> Monitor[监控页面]
    Dashboard --> Chat[对话测试页面]
    Model[兼容 OpenAI 的模型 API] --> Xiaozhi
```

仓库目录：

```text
dashboard/          网页、RDK 数据代理和对话消息接口
xiaozhi-server/      小智 Python 后端及对话消息转发
scripts/            本地初始化、环境检查和提交检查
tests/              网页接口与消息转发自动化测试
docs/               API、二次开发、协作和验证文档
```

## 4. 技术栈与实现原理

- Python 3.10：运行 Dashboard HTTP 服务和小智后端。
- HTML/CSS/JavaScript：实现监控页、对话页和定时数据刷新。
- HTTP 接口：接入视频流、行为状态、环境数据和对话消息。
- WebSocket：由小智后端承载语音交互会话。
- 异步消息队列：对话消息在后台转发，避免网页处理影响语音服务。
- 本地记录文件：网页服务保留最近 200 条对话消息，使用原子写入保存到被 Git 忽略的运行时文件。

Dashboard 将上游接口转换为同源网页接口；浏览器只访问 Dashboard。小智后端在处理用户文字和回复句子时，将消息异步发送到 Dashboard，对话页按配置的间隔读取并展示。页面仅显示记录，不发送消息，也不单独调用对话模型。

## 5. 网页效果展示

### 对话记录页

![对话测试页](docs/assets/dialogue-test.png)

访问地址：<http://127.0.0.1:8088/chat>。页面展示用户消息、机器人回复、时间、设备和会话信息，支持筛选、搜索和界面设置。对话数据与设置只保存在运行服务的电脑中。

### 基础监控页

访问地址：<http://127.0.0.1:8088/>。页面包含监控画面、行为状态和六项传感器数据，并提供对话测试页入口。

## 6. 快速部署

当前电脑已配置 VS Code 一键启动：在“运行和调试”选择“同时启动全部服务”，按 F5 后自动打开登录页。首次按提示创建一次管理员；以后复用已保存的账号与展示设置。管理员和普通用户使用同一登录入口，按账号权限进入界面。手机外网演示选择“同时启动全部服务（手机分享）”。详见 [手机演示指南](docs/MOBILE_DEMO.md)。

用 VS Code 打开整个项目文件夹，按 `Ctrl+Shift+D` 打开“运行和调试”，从上方下拉菜单选择：

| 启动项 | 用途 |
| --- | --- |
| 启动网页服务 | 只启动网页，可查看独立运行的 RDK 视频和环境数据 |
| 同时启动全部服务 | 网页和小智语音服务一起启动，适合设备语音演示 |
| 启动网页服务（手机分享） | 网页与临时手机访问链接 |
| 同时启动全部服务（手机分享） | 网页、小智语音与临时手机访问链接 |

随后按 F5，不必手动输入启动命令。浏览器未自动打开时访问 <http://127.0.0.1:8088/login>。RDK 和传感器端程序需另行运行，F5 不会替你启动它们；RDK 地址变化时更新本地 `.vscode/launch.json` 中的 `RDK_BASE`。

管理员默认进入展示设置页，也可从模块入口查看业务页面；普通用户默认进入开放模块入口，不能导入名单、登记体温、处置事件或修改设置。从某个业务地址跳转登录时，会返回有权限访问的原页面。测试两个角色时，建议一个用普通窗口、另一个用无痕窗口，避免共享同一浏览器会话。

本机 `.vscode/launch.json` 不提交到仓库；其他电脑首次使用须安装 VS Code Python / Python Debugger 扩展、选择解释器，并参考 `docs/vscode-launch.example.json` 建立本机启动配置。

使用 Windows CMD 或 Anaconda Prompt。Python 依赖环境为 `xiaozhi-esp32-server`。

### 6.1 本地配置

登录和基础网页使用 Python 标准库；模型配置读写需 `dashboard/requirements.txt` 中的 PyYAML。仅部署网页的安装步骤见 [手机演示指南](docs/MOBILE_DEMO.md#新电脑首次安装)。完整语音交互服务使用 Python 3.10、根目录 `requirements.txt` 中的依赖和 FFmpeg。首次克隆后执行：

```bat
cd /d D:\ESP32\tongyu-zhishu-v1
conda activate xiaozhi-esp32-server
pip install -r requirements.txt
python scripts\setup_local.py
```

仓库不上传真实 API Key 和模型权重。在 `xiaozhi-server/data/.config.yaml` 中填写模型 API Key；模型接口、模型名称和儿童陪伴提示词模板已经提供。语音服务使用的 SenseVoiceSmall 和 Silero 模型放入 `xiaozhi-server/models`，所需文件见 [模型文件清单](docs/model-files.json)。

### 6.2 启动语音交互服务

```bat
cd /d D:\ESP32\tongyu-zhishu-v1\xiaozhi-server
conda activate xiaozhi-esp32-server
python app.py
```

### 6.3 启动网页服务

```bat
cd /d D:\ESP32\tongyu-zhishu-v1
conda activate xiaozhi-esp32-server
set RDK_BASE=http://192.168.43.54:5000
python scripts/run_dashboard.py
```

`RDK_BASE` 是网页服务使用的数据接口地址，地址变化时只修改启动参数。PowerShell 对应写法为：

```powershell
$env:RDK_BASE="http://192.168.43.54:5000"
python scripts/run_dashboard.py
```

## 7. API 文档

本仓库提供以下网页服务接口：

| 方法 | 地址 | 用途 |
|---|---|---|
| GET | `/api/rdk/video_feed` | 代理监控视频流 |
| GET | `/api/rdk/status` | 读取行为状态 |
| GET | `/api/rdk/sensors` | 读取环境和体温数据 |
| POST | `/api/dialogue/messages` | 接收小智后端的对话消息 |
| GET | `/api/dialogue/messages` | 获取最近 200 条对话消息 |
| GET/POST | `/api/dialogue/config` | 读取或保存对话界面设置 |
| GET | `/health` | 获取 Dashboard 服务状态 |
| GET | `/api/auth/session` | 获取登录状态与 CSRF 验证信息 |
| POST | `/api/auth/register`、`/api/auth/login`、`/api/auth/logout` | 注册、登录、退出 |
| GET/POST | `/api/admin/policy` | 管理员读取或保存展示权限 |
| GET | `/api/config` | 登录后读取 RDK 配置地址 |
| GET/POST | `/api/events` | 查询事件或由管理员创建事件 |
| POST | `/api/events/{id}/status`、`/api/events/{id}/notes` | 管理员处置事件、保存备注 |
| GET | `/api/health/students`、`/api/health/records` | 查询名单和测温记录 |
| POST | `/api/health/import`、`/api/health/records` | 管理员导入名单、登记体温 |
| GET | `/api/reports/daily` | 查询按权限过滤的日报 |

完整请求字段、返回结构和异常状态见 [API 文档](docs/API.md)。

## 8. 二次开发指南

新增监控组件、数据字段、交互页面和后端接口时，可分别扩展：

- `dashboard/index.html`：监控页面结构与刷新逻辑。
- `dashboard/chat.html`：对话页面和筛选逻辑。
- `dashboard/server.py`：网页路由、上游接口代理和数据校验。
- `xiaozhi-server/core/utils/dialogue_monitor.py`：对话消息转发。

具体扩展步骤见 [二次开发指南](docs/EXTENDING.md)。

## 9. 测试与验证

```bat
python -m unittest discover -s tests -v
python scripts\verify_repository.py
```

当前自动化测试覆盖网页路由、RDK JSON 代理、消息格式校验、本机访问限制、设备消息顺序、重复消息、缓存上限和转发异常隔离。浏览器检查覆盖页面渲染和设备筛选。详细结果及软件限制见 [验证记录](docs/VALIDATION.md)。

## 10. 团队开发与开源说明

只有执行 `git commit` 才会产生提交记录，执行 `git push` 后 GitHub 才会显示。三位成员应使用各自的 GitHub 账号和分支提交本人完成的工作，通过 Pull Request 合并，具体流程见 [团队协作说明](docs/DEVELOPMENT.md)。

小智后端来源、导入版本和修改范围见 [第三方来源](THIRD_PARTY.md)。上游小智代码保留其 MIT 许可证。本仓库目前为团队私人协作仓库；公开发布前，应由团队共同确定新增网页代码的许可证，并检查文档、图片和依赖的发布授权。
