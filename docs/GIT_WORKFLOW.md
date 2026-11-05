# Git 工作流与协作记录

更新日期：2026-11-05

## 1. 分支模型

```text
main                稳定、可运行、可演示
 ├─ feat/<topic>    新功能
 ├─ fix/<topic>     缺陷修复
 ├─ docs/<topic>    文档、图表、说明
 └─ chore/<topic>   工具链、依赖、CI
```

- 所有改动从 `main` 新建分支，通过 Pull Request 合并；
- 禁止直接向 `main` 强推或提交未经验证的代码；
- 合并后删除远程分支，保持分支列表简洁。

## 2. 已完成的协作记录

| PR / 分支 | 内容 | 合并方式 |
|---|---|---|
| #1 `feat/monitor-events-ui` | 监控与异常事件界面改版 | Merge pull request |
| #3–#13 系列分支 | 事件契约、健康日报、账号权限、人物估算、实时红外 | Merge pull request |
| #14 `feat/family-safety-events` | 家长安全事件、账号角色、家长日报 | Merge pull request |
| `fix/family-access-reports` | 日报口径修复、账号角色、商家传感器、开题对照 | 合并到 `main` |

后续任务统一在 GitHub Issues 中登记，PR 描述关联 `Closes #id`。

## 3. 提交规范

- 使用 Conventional Commits，英文书写：
  `feat(events): add participant assignment by student name`；
- 一次提交只做一件事；格式化、重命名与功能改动分开；
- 提交前运行 `pre-commit`（见根目录 `.pre-commit-config.yaml`）；
- 历史提交（2026-11-04 之前）早于本规范，存在中英混用，不再改写历史。

## 4. Issue 使用

- 模板：缺陷、功能、任务三类（`.github/ISSUE_TEMPLATE/`）；
- 标签：
  - 类型：`type:feature`、`type:bug`、`type:docs`、`type:test`
  - 模块：`area:events`、`area:health`、`area:family`、`area:web`、`area:ci`
  - 优先级：`priority:high`、`priority:medium`、`priority:low`
- 测试、设计、文档任务也建 Issue，并在 PR/评论中留下评审记录，作为工作量证据；
- 可直接使用的 Issue 草案见 [ISSUES_DRAFT.md](ISSUES_DRAFT.md)。

## 5. 发布与版本

- 可演示版本打轻量标签：`v0.1-demo`、`v0.2-defense`；
- 发布说明写清：新增功能、修复、已知限制、验证命令；
- 不把运行数据、模型权重、日志、密钥打进发布包。

## 6. 大文件与敏感信息

- `.gitignore` 已排除运行数据、抓拍、模型、日志和本地配置；
- 提交前运行 `python scripts/verify_repository.py`，CI 也会执行；
- 单文件超过 1 MiB 的二进制资源需说明来源和必要性（当前仅有文档截图和上游提示音）。
