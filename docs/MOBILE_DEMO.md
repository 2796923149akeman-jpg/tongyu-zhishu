# 手机演示：注册、登录与展示设置

目标：电脑运行网页服务后，把链接发给老师；老师在手机浏览器注册用户名和密码，再登录查看管理员开放的内容。无需安装手机客户端。

## 日常使用：VS Code 按 F5

用 VS Code 打开 `D:\ESP32\tongyu-zhishu-v1`，在左侧“运行和调试”的下拉框中选择启动项，然后按 F5：

| 启动项 | 行为 |
| --- | --- |
| 启动网页服务 | 启动网页并自动打开统一登录页 |
| 同时启动全部服务 | 同时启动小智与网页，自动打开登录页 |
| 启动网页服务（手机分享） | 启动网页，自动打开登录页，并生成手机 HTTPS 链接 |
| 同时启动全部服务（手机分享） | 同时启动小智、网页和手机分享 |

首次启动只需在自动出现的终端中输入一次管理员用户名、密码及确认密码，不用输入启动命令。以后按 F5 会直接沿用账号和设置。普通用户在同一个登录页注册、登录：管理员登录默认进入展示设置页，普通用户默认进入已开放模块的入口。登录页不会要求手选身份，角色由账号决定；如果从某个业务页面跳转登录，成功后会回到允许访问的站内页面。

管理员账号、普通用户账号和保存的展示开关都存放在运行电脑的 `dashboard/auth_config.json` 中。密码保存为加盐哈希；保留这个本地文件，就不会因关闭 VS Code、电脑重启或重新启动服务而丢失。初始开关只是首次缺少配置时的默认值，后续可随时修改，重启不会重置。服务重启会清除登录会话，需要用已有账号重新登录，不需要重新注册。

手机分享项会在终端打印“手机登录 / 注册链接”。老师用手机打开该链接即可；本机使用不带“手机分享”的启动项即可。停止调试时会结束所启动的服务；VS Code Python 调试器会管理并终止子进程，包括分享进程。账号与设置文件会保留。

本机的 `.vscode/launch.json` 已更新；该目录按仓库规则不提交。其他电脑可参考 `docs/vscode-launch.example.json` 配置同名启动项，并按实际路径调整 Python 环境。下面的终端脚本方式作为可选入口保留。

## 已实现的范围

- 注册用户固定为演示查看者，不能注册成管理员；所有演示账号共用管理员设置的展示权限。
- 五个模块各有开关：实时监控、异常事件、对话与情绪、学生测温、当日日报。
- 摄像头画面另有开关。“实时监控”指整个页面，包含温度、空气质量、设备状态等；“摄像头画面”就是该页面的视频。视频关闭不影响传感器数据。
- 对话原文另有开关。关闭后，接口只保留情绪等结构化结果；隐藏原文、由原文生成的会话标题、会话总结与分析理由。日报中的演示对话摘录也不展示。
- 初始开放全部五个模块，摄像头画面及对话原文初始关闭。管理员不受这些展示开关限制。保存后，查看者在约 5 秒内自动刷新；接口权限立即生效，已有视频流在读取下一段时重新检查权限。
- 已接入队友的事件、名单、手动测温和日报接口；读取受模块权限控制，写入仅限管理员。日报也会隐藏被关闭模块的数据与未开放的对话原文。设备体温自动关联学生仍未实现。

## 先在电脑预览

在项目目录的 PowerShell 中运行：

```powershell
.\scripts\start_mobile_demo.ps1
```

第一次会在终端提示你创建管理员用户名和密码，密码输入不会显示。随后打开 <http://127.0.0.1:8088/login>，用管理员账号登录，在 <http://127.0.0.1:8088/admin> 设置展示范围。

管理员由本机工具创建，没有面向外部的管理员注册入口。普通注册不需要手机号、邮箱或审批；密码为 6–128 位。第一版没有找回密码、账号删除或账号管理界面。需要另建管理员可运行：

```powershell
D:\Anaconda\envs\xiaozhi-esp32-server\python.exe dashboard/manage_access.py
```

账号更改后应重启服务。用户名和加盐密码哈希仅存放在被 Git 忽略的 `dashboard/auth_config.json`。不要把该文件发给别人。

## 生成老师可直接打开的外网链接

启动脚本会优先使用项目 `output/tools/cloudflared.exe`，也可使用 PATH 中的工具或 `-CloudflaredPath` 指定的文件。本次工作区已准备官方工具并核对发布包的 SHA256；复制仓库到其他电脑时，需另从 [cloudflared 官方下载页](https://developers.cloudflare.com/tunnel/downloads/)获取程序。运行：

```powershell
.\scripts\start_mobile_demo.ps1 -Share
# 若 cloudflared 不在 PATH 中：
.\scripts\start_mobile_demo.ps1 -Share -CloudflaredPath 'D:\tools\cloudflared.exe'
```

启动窗口会显示 `https://…trycloudflare.com/login`，把它发给老师。老师点击“注册”，自行填写用户名、密码，再登录。电脑需要联网且保持唤醒；网页服务和隧道也需要持续运行。按 Ctrl+C 停止服务与分享。脚本只停止它自己启动的进程，不会结束已有的其他服务。

这是一个可从互联网访问的登录入口。所有人都能注册，但只能看你开放的内容。演示前用普通账号确认展示范围，尤其是视频和真实对话；管理员登录时能看全部内容，不能用管理员页面判断老师能看什么。

[Quick Tunnel 官方文档](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)说明：不需要域名或 Cloudflare 账号，每次创建会得到不同的临时地址，停止进程后地址失效，且不保证可用性。这里准备的是启动脚本，代码修改和测试本身不会启用外网分享。实际网络可达性、摄像头流畅度必须在老师使用的网络验收；当前没有完成真实手机外网验收。

建议验收：手机关闭 Wi-Fi，使用移动数据访问链接 → 注册登录 → 查看已开放模块 → 管理员关闭一个模块或视频 → 手机页面自动更新 → 退出后再打开业务地址，应回到登录页。

## 会话与运行配置

- 默认只监听 `127.0.0.1:8088`，通过隧道转发；不开放路由器端口。
- Cookie 默认启用 Secure、HttpOnly、SameSite=Lax，密码使用 Python 标准库 scrypt 加盐哈希。
- 空闲 30 分钟或登录满 8 小时过期；退出及重启服务都会使会话失效。
- 登录与注册均需要同源请求和页面 CSRF 验证；管理员写操作也需要 CSRF。登录错误使用统一提示，失败 5 次后该用户名暂限 10 分钟；注册亦有限速。
- 小智的 `POST /api/dialogue/messages` 仍允许本机机器写入，无需浏览器登录；公网 Host、转发请求头和非回环来源都会被拒绝。不要给隧道配置把公网 Host 改写成本机 Host 的规则。
- `DASHBOARD_AUTH_FILE` 可指定本地账号文件；`DASHBOARD_COOKIE_SECURE=0` 只用于本机 HTTP 调试。启动脚本本机预览时使用此设置，`-Share` 时强制开启 Secure。不会根据请求头自动降级。
- 可用 `-Port 8089` 改网页端口；如小智也需要上传，应同步设置其 Dashboard 地址。默认保留 8088，无需改设备协议。
- 日志放在已忽略的 `output/`，账号文件和临时文件也已加入忽略规则与仓库检查。

## 验证命令

```powershell
D:\Anaconda\envs\xiaozhi-esp32-server\python.exe -m unittest discover -s tests -v
D:\Anaconda\envs\xiaozhi-esp32-server\python.exe scripts/verify_repository.py
```

新增测试覆盖注册角色、登录、Cookie、CSRF、来源、会话空闲及绝对过期、退出、登录限速、模块与视频权限、原文过滤及本机消息上传。登录功能未新增 Python 第三方依赖；模型配置读写需要 PyYAML，安装方式见下文。

## 新电脑首次安装

Python 使用 3.10 或更新版本。在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\.venv\Scripts\python.exe scripts/run_dashboard.py
```

仅登录、页面和本地词库可用标准库运行；上述轻量依赖保证模型 YAML 配置也能读写。完整语音服务仍需根目录 `requirements.txt`、FFmpeg、模型文件和本机模型密钥配置，见主 README；不需要为登录重新安装整套语音依赖。

VS Code 安装 Python 与 Python Debugger 扩展，执行“Python: Select Interpreter”选择安装了依赖的解释器。首次将 `docs/vscode-launch.example.json` 复制为 `.vscode/launch.json`（已有配置时手动合入，勿覆盖自己的路径），按 F5；模板不包含固定 Python 路径，启动时填写实际 RDK 地址。Conda 用户先激活环境再打开 VS Code，以继承本机 DLL 路径。

测试依赖单独安装：`python -m pip install -r tests/requirements.txt`，再执行本文验证命令。手机分享额外需要 cloudflared；它不是 Python 依赖，也不随仓库上传。

后续队友新增接口时：GET 路由须位于 `require_session` 之后并登记 `route_module`；POST 写入须检查管理员和 CSRF；仅本机对话上传使用独立入口。涉及日报聚合时同时核对模块开关和原文过滤。不要用队友的整个 server.py 覆盖本文件；正常合并提交后运行全部测试。
