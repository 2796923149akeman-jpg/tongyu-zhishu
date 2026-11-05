# 贡献指南

本文档约定本仓库的分支、提交、评审、测试与发布流程。提交前请先阅读
[代码风格](docs/CODE_STYLE.md)。

## 1. 本地环境

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tests\requirements.txt
.\.venv\Scripts\python.exe -m pip install pre-commit
pre-commit install
```

运行网页：

```powershell
$env:RDK_BASE = "http://192.168.43.54:5000"
.\.venv\Scripts\python.exe scripts\run_dashboard.py
```

运行测试与仓库自检：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\verify_repository.py
.\.venv\Scripts\ruff.exe check dashboard scripts tests
```

## 2. 分支模型

| 分支 | 用途 | 示例 |
|---|---|---|
| `main` | 可运行、可演示的稳定分支 | — |
| `feat/<topic>` | 新功能 | `feat/family-events` |
| `fix/<topic>` | 缺陷修复 | `fix/report-date` |
| `docs/<topic>` | 文档、示例与说明 | `docs/architecture` |
| `chore/<topic>` | 构建、依赖、工具链 | `chore/ruff` |

- 每个分支只做一件事，合并后删除；
- 合并到 `main` 前必须提 PR，至少一名其他成员评审；
- 紧急修复同样走 PR，不直接推 `main`。

## 3. 提交信息规范

使用 **Conventional Commits**，英文书写，`type(scope): summary`：

```text
feat(events): add participant assignment by student name
fix(reports): keep the original event source in daily report
docs(security): document CSRF and evidence permissions
test(family): cover parent snapshot scoping
chore(ci): run ruff in the checks workflow
```

- `type`：`feat`、`fix`、`docs`、`test`、`refactor`、`chore`、`perf`、`build`、`ci`；
- `scope` 可选：`events`、`health`、`dialogue`、`family`、`reports`、`web`、`ci`；
- 摘要不超过 72 个字符，动词开头、小写、末尾不加句号；
- 正文说明“为什么”和影响范围，最多 3 段；
- 一个提交只做一个逻辑改动；格式化、重命名、功能变更分开提交；
- 不提交密钥、真实儿童数据、运行日志和构建产物。

> 说明：2026-11-04 之前的提交早于本规范，历史信息中英混用；新提交统一按上述格式。

## 4. 提交前检查

`pre-commit install` 后，`git commit` 会自动执行：

- 去除行尾空格、补齐文件末尾换行；
- 检查 YAML/JSON 语法、私钥和大文件；
- `ruff check --fix`（仅 `dashboard/`、`scripts/`、`tests/`）。

也可以手动执行：

```powershell
pre-commit run --all-files
```

## 5. PR 流程

1. 从 `main` 新建分支；
2. 提交时关联 Issue（`Closes #12`）；
3. PR 描述使用模板：改动内容、测试方式、截图/录屏、风险与回滚；
4. CI 必须通过（单元测试、仓库自检、ruff）；
5. 至少一名成员评审通过后合并，推荐 Squash 或 Rebase；
6. 合并后删除分支并更新相关文档。

## 6. Issue 约定

- 模板：`.github/ISSUE_TEMPLATE/`（缺陷、功能、任务）；
- 标签：`type:feature`、`type:bug`、`type:docs`、`area:events`、`area:health`、
  `area:family`、`area:web`、`priority:high/medium/low`；
- 测试、设计、文档任务也建 Issue，便于统计工作量；
- 评审意见留在 PR/Issue 中，作为团队贡献证据。

## 7. 人工智能辅助开发

- 允许使用大模型辅助编码、测试与文档，但提交者必须理解并验证生成内容；
- 不把真实 API Key、儿童姓名、对话原文或截图发给外部模型；
- AI 生成的代码必须通过全部测试和人工评审，文档中的数字以实际测量为准；
- 在 PR 描述中简要说明使用了哪些工具和验证方式。
