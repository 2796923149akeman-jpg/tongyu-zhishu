# 二次开发指南

## 新增监控数据字段

1. 确认上游 `/api/iot_payload` 返回稳定的 JSON 字段。
2. 在 `dashboard/index.html` 增加展示元素，并为数值元素设置唯一 `id`。
3. 在 `refreshSensors()` 中读取字段并调用 `display()`。
4. 为字段缺失和非数值情况保留 `--` 展示。
5. 在 `tests/test_dialogue.py` 的路由测试中加入对应示例字段。
6. 同步更新 `docs/API.md`。

## 新增监控页面组件

页面组件写在 `dashboard/index.html`。沿用当前 `.box`、`.title`、`.sensor` 等样式，可以保持页面一致。组件数据通过 Dashboard 的同源 `/api/...` 接口获取，避免浏览器直接访问不同地址产生跨域配置。

## 新增 Dashboard 接口

1. 在 `dashboard/server.py` 的 `Handler` 中实现独立处理函数。
2. 在 `do_GET()` 或 `do_POST()` 中登记明确路径。
3. 校验请求体类型、大小、必填字段和长度。
4. 使用 `send_json()` 返回统一 JSON；不要向响应写入 API Key、口令或本机私有配置。
5. 添加正常、错误和越权请求测试。
6. 在 `docs/API.md` 记录方法、路径、请求和响应示例。

## 新增对话页面功能

对话页位于 `dashboard/chat.html`，当前每秒读取 `/api/dialogue/messages`。新增筛选或显示字段时，应使用 `textContent` 写入外部文本，避免把消息当作 HTML 解释。消息缓存由服务端 `deque(maxlen=200)` 管理。

情绪词库位于 `dashboard/emotion_lexicon.json`。可在 `categories` 中补充日常表达，在 `attention.watch` 和 `attention.urgent` 中增加经过人工确认的留意短语。每次修改后运行 `python -m unittest discover -s tests -v`；词库命中只是提示人工核实，不应当被描述为诊断结论。

模型调用、词库评分与会话总结位于 `dashboard/analysis.py`。模型异常必须回退到本地结果，任何模型或网络调用都不能放到 ESP32 消息接收线程中。

若需要历史记录，应新建明确的数据存储模块，定义保存期限、并发写入、隐私字段和清理策略，而不是直接把当前内存队列写入 Git 跟踪文件。

## 调整对话消息转发

转发模块位于 `xiaozhi-server/core/utils/dialogue_monitor.py`。当前使用单个后台线程和有界队列，Dashboard 不可用时放弃本条消息，不阻塞语音处理。修改时应保持：

- 网络请求不在音频协程中同步等待；
- 队列有上限，避免网页异常导致内存持续增长；
- 消息编号唯一；
- 文本和标识字段有长度限制；
- 转发失败不改变原有对话结果。

## 配置与敏感信息

公开模板为 `xiaozhi-server/config.example.yaml`，本机配置为被 Git 忽略的 `xiaozhi-server/data/.config.yaml`。新增账号、密钥或私有地址时使用本机配置或环境变量，并同步检查 `.gitignore` 和 `scripts/verify_repository.py`。

## 提交前检查

```bat
python -m unittest discover -s tests -v
python scripts\verify_repository.py
git diff
git status
```

接口行为变化时，应同时提交代码、测试和 API 文档。
