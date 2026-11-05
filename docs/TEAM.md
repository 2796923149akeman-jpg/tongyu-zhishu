# 团队分工与工作量度量

更新日期：2026-11-05

## 1. 成员与模块

| 姓名 | GitHub 账号 | 主要模块 | 说明 |
|---|---|---|---|
| 靳能州 | `2796923149akeman-jpg` | 对话、小智后端集成、账号与部署 | [对话看板](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/ee920dd)、[账号与启动](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/3ada8b1) |
| 郁继鑫 | `yanjuxia` | 监控、事件契约、实时红外与家长事件 | [事件契约 PR #7](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/7)、[家长安全 PR #14](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/14) |
| 韩欣然 | `yanghesu99` | 测温和日报页面、环境告警、抓拍重试、工程规范 | [测温与日报 PR #2](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/2)、[环境异常事件](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/b566fb6)、[CI 与协作规范](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/38bcf53) |

## 2. 客观度量（`python scripts/team_metrics.py`）

以工程整改前后的核对版本 `934375e` 固定统计范围。该版本共 82 个提交，其中 66 个为非合并提交。下表的变更量排除初始导入提交 `c499217`。

| 成员 | 非合并提交总数 | 导入后提交 | 新增行 | 删除行 | 文件变更次数 |
|---|---:|---:|---:|---:|---:|
| `2796923149akeman-jpg` | 30 | 29 | 5693 | 1510 | 152 |
| `yanjuxia` | 15 | 15 | 11421 | 369 | 114 |
| `yanghesu99` | 21 | 21 | 9327 | 122 | 126 |

说明：

- 同一文件在多个提交中修改会计入多次。行数只统计 Git 可计数的文本变更。
- 初始导入包含上游代码和基线资料，剔除该提交后仍保留后续对上游代码的实际修改。
- 测试、设计、文档和联调以用例、图表、记录或评审证据补充，分开核对交付。

## 3. 最终绩效分配（团队已确认）

评分权重：功能与代码 50%、测试与质量 20%、文档与设计 20%、协作与评审 10%。

| 姓名 | GitHub 账号 | 最终 KPI | 主要依据 |
|---|---|---:|---|
| 靳能州 | `2796923149akeman-jpg` | 40% | 语音、账号和启动集成，设备联调与部署工作 |
| 郁继鑫 | `yanjuxia` | 35% | 监控与事件页、事件契约、家长权限、红外接口及关联测试 |
| 韩欣然 | `yanghesu99` | 25% | 测温和日报页、环境告警、模拟 RDK、抓拍重试与工程规范 |

**为什么这样分**：以提交数和目录分布为基础，结合模块复杂度（语音后端与设备联调、
事件链路、权限与测试）调整；三人均在核心模块有可见提交，避免“只一人提交”的问题。

最终分配于 2026-11-05 经团队确认，比例为 **40% / 35% / 25%**。

## 4. 协作与评审证据

- PR：#1（监控界面）、#14（家长安全事件）等，合并记录见 `git log --merges`；
- 分支：`feat/*`、`fix/*`、`docs/*`，见 `docs/GIT_WORKFLOW.md`；
- Issue 与交付关联示例：[Issue #4](https://github.com/2796923149akeman-jpg/tongyu-zhishu/issues/4) → [PR #7](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/7)。其余草案见 [Issue 草案](ISSUES_DRAFT.md)。
- 测试和设计举例：[家长隐私回归](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/603e19d)、[系统架构与 UML](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/d4ed835)。
- 评审流程见 [Git 工作流](GIT_WORKFLOW.md)，历史评审以相应 PR 的实际记录为准。

## 5. 复现度量

```powershell
python scripts/team_metrics.py --ref 934375e
python scripts/team_metrics.py --ref 934375e --after c499217 --json
git shortlog -sn --no-merges 934375e
```

建议在答辩材料中同时给出：提交数、净增行、目录分布、Issue/PR 数量、测试与文档产出。
