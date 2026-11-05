# 测试计划与用例

更新日期：2026-11-05

## 1. 测试策略

| 层次 | 方式 | 目标 |
|---|---|---|
| 单元/契约 | `unittest` 直接调用函数 | 事件契约、状态转换、姓名解析、阈值判断 |
| 接口集成 | 启动真实 `ThreadingHTTPServer`，使用临时文件 | 路由、权限、CSRF、持久化、家长隔离 |
| 静态检查 | 读取 HTML/JS 源文件 | 关键控件、事件绑定、无遗漏元素 ID |
| 仓库自检 | `scripts/verify_repository.py` | 敏感文件、超大文件、硬编码凭据、语法 |
| 手工/设备 | 浏览器与真实设备 | 页面渲染、RDK/STM32/ESP32 全链路 |

自动化测试使用模拟上游与临时目录，不依赖真实设备、模型或付费 API。

## 2. 运行方式

```powershell
.\.venv\Scripts\python.exe -m pip install -r tests\requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\verify_repository.py
.\.venv\Scripts\ruff.exe check dashboard scripts tests
```

CI：`.github/workflows/checks.yml` 在 push/PR 时执行单元测试、仓库自检和 ruff。

## 3. 用例分布（共 117 项）

| 测试文件 | 数量 | 覆盖内容 |
|---|---|---|
| `test_access.py` | 16 | 角色、模块开关、CSRF、限流、会话、家长/商家范围 |
| `test_analysis.py` | 4 | 本地词库、否定语境、模型配置校验 |
| `test_commit_policy.py` | 4 | Conventional Commits、标题长度、Merge 例外和 commit-msg 文件 |
| `test_dialogue.py` | 12 | 消息写入/去重、情绪、摘要、删除、对话关注事件 |
| `test_environment_events.py` | 4 | 离线、过期、eCO₂/TVOC、恢复与去重 |
| `test_event_contract.py` | 9 | 字段校验、状态转换、证据 URL、日报映射 |
| `test_events.py` | 13 | 创建/查询/去重、参与者、抓拍状态与重试、播报记录 |
| `test_family_events.py` | 11 | 家长隔离、多人姓名过滤、截图越权、家长日报、商家字段 |
| `test_health_api.py` | 7 | 名单导入、登记、复测、查询、权限 |
| `test_health_realtime.py` | 5 | 红外新鲜度、自动入库、去重、异常状态 |
| `test_health_report.py` | 7 | 日报统计、跨日、班级筛选、导出数据 |
| `test_monitor_events_ux.py` | 8 | 事件页控件、快捷筛选、证据与重试区域、DOM 完整性 |
| `test_person_type.py` | 9 | 可选人物估算进程与接口 |
| `test_startup.py` | 3 | 管理员初始化、F5 重启与后台环境监控 |
| `test_weather.py` | 5 | 天气工具调用与失败处理 |

## 4. 需求覆盖

| 开题能力 | 主要用例 |
|---|---|
| 开放式模型接入 | `test_analysis.py`、`test_dialogue.py`（模型配置脱敏、回退） |
| 对话与情绪 | `test_dialogue.py`、`test_analysis.py` |
| 视觉与环境巡护 | `test_environment_events.py`、`test_monitor_events_ux.py` |
| 统一事件处置 | `test_events.py`、`test_event_contract.py`、`test_family_events.py` |
| 名单与体温 | `test_health_api.py`、`test_health_realtime.py`、`test_health_report.py` |
| 日报与家长端 | `test_health_report.py`、`test_family_events.py` |
| 安全与权限 | `test_access.py`、`test_family_events.py` |

## 5. 验收命令与通过标准

- 单元测试：`Ran 117 tests ... OK`；
- 仓库自检：`{"errors": 0}`；
- ruff：`All checks passed!`；
- 浏览器手工检查：见 `docs/VALIDATION.md` 与 `docs/MONITOR_EVENTS_UI.md`；
- 真实设备：见 `docs/DEVICE_VALIDATION.md`。

## 6. 未覆盖与后续

- 真实硬件链路（摄像头、传感器精度、ESP32 语音）需现场联调；
- 浏览器端到端自动化（Playwright）尚未接入，目前为静态检查 + 手工验证；
- 情绪模型准确率需要人工标注样例，当前仅有小规模本地评估（见 `docs/EXPERIMENTS.md`）。

## 7. 覆盖率

使用 `coverage.py` 在本地测量（临时目录、隔离测试）：

```powershell
python -m pip install coverage
python -m coverage run --source=dashboard -m unittest discover -s tests
python -m coverage report -m
```

2026-11-05 结果：

| 模块 | 覆盖率 |
|---|---:|
| `access_control.py` | 91% |
| `event_contract.py` | 88% |
| `health_realtime.py` | 83% |
| `person_type.py` | 88% |
| `server.py` | 79% |
| **合计** | **80%** |

未覆盖部分主要是异常分支、真实网络/设备路径和可选人物估算的启动分支。
覆盖率是参考指标，不作为唯一质量标准。
