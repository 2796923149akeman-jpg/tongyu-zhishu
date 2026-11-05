# 代码风格

更新日期：2026-11-05

本仓库以 Python 标准库 + 原生 HTML/CSS/JavaScript 为主，工具配置见
`pyproject.toml`、`.editorconfig` 和 `.pre-commit-config.yaml`。

## 1. Python

- 遵循 PEP 8；行宽软上限 120 字符（长字符串、HTML 模板除外）。
- 使用 4 空格缩进、UTF-8、LF 换行；文件末尾保留一个空行。
- 导入顺序：标准库 → 第三方 → 本地模块，组间空一行；`server.py` 因先插入
  项目路径再导入本地模块，保留既有顺序。
- 命名：模块/函数/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_CASE`。
- 公共函数建议写类型标注和中文 docstring，说明输入、输出和失败条件。
- 使用 `pathlib.Path` 处理路径，不拼接字符串路径。
- 异常只捕获可处理的类型；后台线程和通知失败必须记录日志，不能静默吞掉。
- 时间统一使用带时区的 ISO 8601（`Asia/Shanghai`），日期统计用 `date_key`。
- 不把端口、IP、密钥、阈值写死在业务逻辑里；优先使用环境变量，默认值集中在
  `dashboard/server.py` 顶部并在 [配置说明](CONFIGURATION.md) 中登记。
- 运行数据（`events.json`、`health_students.json`、`auth_config.json`、抓拍）
  只能写入被 `.gitignore` 忽略的运行时路径。

检查命令：

```powershell
.\.venv\Scripts\ruff.exe check dashboard scripts tests
```

## 2. JavaScript

- 使用 ES2020 语法和 IIFE 包裹页面脚本，避免污染全局。
- 只使用 `const` / `let`，不使用 `var`。
- 动态文本必须通过 `textContent` 写入，禁止把接口内容拼进 `innerHTML`。
- 时间显示统一 `Intl.DateTimeFormat` + `timeZone: "Asia/Shanghai"`。
- 网络请求统一 `fetch` + `AbortController` 超时；错误提示面向用户、可读。
- 共享逻辑放 `dashboard/access.js`，页面脚本只保留自身交互。

## 3. HTML / CSS

- 语义化标签（`header`、`main`、`section`、`nav`），交互控件加 `aria-*`。
- 颜色、间距使用 CSS 变量（`--brand`、`--ink` 等），不散落魔法值。
- 页面内联 `<script>` 仅用于该页交互；可复用逻辑抽到独立 `.js`。
- 不引入外部 CDN 依赖，保持离线可运行。

## 4. 数据与接口

- JSON 字段使用 `snake_case`；时间字段为带时区的 ISO 8601。
- 事件字段以 `dashboard/event_contract.py` 为准，新增字段必须同步
  [API 文档](API.md) 和契约测试。
- 接口错误统一 `{"ok": false, "error": "...", "detail": "..."}`。
- 写接口要求管理员会话、同源和 `X-CSRF-Token`；读取按模块权限过滤。

## 5. 安全与隐私

- 不在日志中输出请求体、Cookie、Authorization、API Key 或对话原文。
- 不提交真实儿童照片、姓名、对话和健康数据；演示使用模拟或脱敏数据。
- 证据图片、抓拍目录、运行配置必须在 `.gitignore` 中排除。
- 家长端只返回本人孩子的事件与授权截图；越权统一 404/403。

## 6. 提交前检查清单

- [ ] `ruff check` 通过
- [ ] `python -m unittest discover -s tests -v` 通过
- [ ] `python scripts/verify_repository.py` 通过
- [ ] 无新增密钥、运行数据、日志和大文件
- [ ] 相关文档已更新（API、验证记录、README）
- [ ] 提交信息符合 [贡献指南](../CONTRIBUTING.md)
