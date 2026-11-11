# 团队分工与工作量度量

更新日期：2026-11-11

## 1. 成员与模块

| 姓名 | GitHub 账号 | 主要职责 | 代表交付与证据 |
|---|---|---|---|
| 靳能州 | `2796923149akeman-jpg` | 对话设计、小智后端集成、账号与部署、功能检查和合并 | [对话看板](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/ee920dd)、[对话批量关联](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/20)、[账号与启动](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/3ada8b1)、[工程质量改进合并](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/21) |
| 郁继鑫 | `yanjuxia` | 监控、事件契约、实时红外、家长事件与权限测试 | [事件契约 PR #7](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/7)、[家长安全 PR #14](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/14) |
| 韩欣然 | `yanghesu99` | 测温和日报页面、环境告警、模拟 RDK、抓拍重试、工程规范 | [测温与日报 PR #2](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/2)、[环境异常事件](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/b566fb6)、[CI 与协作规范](https://github.com/2796923149akeman-jpg/tongyu-zhishu/commit/38bcf53) |

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

## 3. 贡献评价口径

三位成员采用相同的评价口径。按各自职责核对功能交付、测试与质量、文档与设计、协作与评审。
用提交、PR、Issue、测试用例和联调记录佐证实际工作。提交数与变更行数用于描述可统计的代码变更，
评估贡献时结合模块职责与交付成果。

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
