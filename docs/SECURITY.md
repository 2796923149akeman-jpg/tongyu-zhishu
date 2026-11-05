# 信息安全设计

更新日期：2026-11-05

系统面向幼儿园教师、家长和演示人员，涉及儿童名单、健康记录、对话和抓拍。
本文档描述威胁模型、已实施控制、已知限制和部署建议。

## 1. 资产与威胁

| 资产 | 风险 | 影响 |
|---|---|---|
| 账号与会话 | 弱口令、暴力破解、会话劫持 | 越权访问 |
| 学生名单/体温 | 未授权读取或导出 | 隐私泄露 |
| 对话与情绪 | 原文泄露、外部模型滥用 | 隐私与合规风险 |
| 事件抓拍 | 图片被越权查看或转发 | 儿童肖像风险 |
| 家长端数据 | 看到其他孩子的事件 | 家庭隐私泄露 |
| 设备令牌/模型密钥 | 硬编码或进入仓库 | 服务被滥用 |
| 通知网关 | 伪造事件触发播报 | 骚扰与误导 |

## 2. 已实施的安全控制

| 控制 | 实现位置 | 说明 |
|---|---|---|
| 密码哈希 | `access_control.py` | scrypt + 随机盐，不保存明文 |
| 会话 Cookie | `access_control.py` | `HttpOnly`、`SameSite=Lax`、可配 `Secure`，8 小时/30 分钟空闲过期 |
| CSRF | `server.py` | 写接口校验 `X-CSRF-Token`，Token 随会话下发 |
| 同源校验 | `server.py` | 校验 `Origin`/`Sec-Fetch-Site`，拒绝跨站写请求 |
| 登录限流 | `access_control.py` | 用户名 5 次/10 分钟、来源 IP 60 次/10 分钟 |
| 角色与模块权限 | `access_control.py` | 管理员/演示/家长/商家/待分配；模块开关 |
| 家长数据隔离 | `server.py` | 只返回绑定孩子的事件、日报与授权截图 |
| 证据权限 | `server.py` | 事件截图需视频权限；家长还需事件参与关系与截图开关 |
| 设备令牌 | `server.py` | `X-Device-Token` 与浏览器会话分离，仅允许本机/受控来源 |
| 安全响应头 | `server.py` | `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`、CSP `frame-ancestors` |
| 输入校验 | `event_contract.py`、`server.py` | 字段长度、枚举、时间格式、证据 URL 同源/栅格图片 |
| 密钥脱敏 | `analysis.py`、`server.py` | 页面只返回 `api_key_set`，不返回密钥 |
| 仓库卫生 | `.gitignore`、`verify_repository.py` | 运行数据、模型、日志、密钥、抓拍不入库；CI 检查 |
| 供应链 | `THIRD_PARTY.md`、`docs/SUPPLY_CHAIN.md` | 记录来源、版本、许可证与修改范围 |

## 3. 关键校验点

- 写接口：`require_session(path, admin=True, write=True)`，管理员 + 同源 + CSRF；
- 读取接口：按角色与模块开关过滤；家长走独立 `/api/family/*` 路由；
- 证据：`has_snapshot` 仅在具备视频权限时返回；家长截图接口重新校验事件归属；
- 设备推送：令牌长度 ≥ 24 位、恒定时间比较、来源与转发头校验；
- 通知：仅允许 http/https，超时 3 秒，失败只记录不重试风暴；
- 日志：只记录方法/路径/状态，不打印请求体、Cookie 或 Authorization。

## 4. 已知限制

- 默认使用 HTTP，公网演示需通过 cloudflared 等 HTTPS 隧道；生产环境应加 TLS。
- 账号、名单、事件存储在本地 JSON，依赖操作系统文件权限，未做磁盘加密。
- 没有多因素认证、密码找回和会话管理界面；管理员账号由本机初始化创建。
- 没有集中式审计日志和告警；事件处理历史可追溯，但不覆盖所有管理操作。
- 依赖版本固定但未在 CI 中执行漏洞扫描（可增加 `pip-audit`）。
- 第三方模型/语音服务会接收必要文本或音频，需遵守其隐私条款。

## 5. 部署建议

1. 仅在内网或受控网络演示，使用 HTTPS 隧道时保持 `DASHBOARD_COOKIE_SECURE=1`；
2. 设置强管理员密码，定期更换 `HEALTH_DEVICE_TOKEN`；
3. 不在公网暴露 RDK 5000 端口与小智 8000/8003 端口；
4. 演示结束清理 `dashboard/events.json`、抓拍、对话与名单中的真实数据；
5. 发布前运行 `python scripts/verify_repository.py`，确认无敏感文件与密钥。

## 6. 漏洞报告

发现安全问题请在团队内部 Issue 中标注 `security`，不要公开披露真实儿童数据或
密钥；修复前避免在生产演示环境复现。
