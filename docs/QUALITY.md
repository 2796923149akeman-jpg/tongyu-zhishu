# 仓库质量检查与验证入口

## 目录职责

| 入口 | 内容 |
|---|---|
| `dashboard/` | 团队网页、业务接口、事件契约、权限和持久化模块 |
| `xiaozhi-server/` | 上游语音服务及集成修改；来源与差异见供应链说明 |
| `tests/` | 使用临时目录和模拟上游的单元、接口及静态页面检查 |
| `scripts/` | 启动、模拟演示、自检、提交规范及团队统计工具 |
| `docs/` | 设计、用户手册、测试、部署、验证边界与分工 |
| `.github/` | CI 工作流、Issue 与 PR 模板 |
| `output/` | 本地生成报告，已被 Git 忽略，不提交测试产物或运行数据 |

目录分开并不代表业务完全解耦。当前 `server.py` 仍集中了多类业务；改进时应保持接口兼容并运行回归。

## 自动化检查

[工作流入口](https://github.com/2796923149akeman-jpg/tongyu-zhishu/actions/workflows/checks.yml)。
每次 push、PR 或手动运行均检查：

- Ubuntu / Python 3.10、Windows / Python 3.10、Ubuntu / Python 3.12 三种环境的完整测试与覆盖率；
- 仓库敏感文件、格式及提交标题规则；
- 独立 Ruff 检查。所有必需检查应通过后再合并。

Dashboard 总语句覆盖率最低为 80%，未达到时 CI 失败；本轮 Windows / Python 3.13.9
实测 125 项测试通过，覆盖 2497 / 3095 条语句（80.68%）。这是语句覆盖率，
不代表分支覆盖率、真实设备准确率或所有交互均已测试。CI 中其他环境的结果以对应报告为准。

同分支新提交会取消旧检查，环境矩阵不会因某一个环境失败而取消其余环境。
测试任务有 15 分钟上限，避免无限等待。测试输出经过管道时保留失败退出码。

打开对应运行，在 Artifacts 下载 `quality-<系统>-py<版本>`，保存 14 天：

- `tests.log`：逐项测试结果及失败堆栈；
- `coverage.txt`：模块覆盖率摘要；
- `coverage.xml`：供工具读取的覆盖率；
- `html/`：解压后打开 `index.html`，查看未覆盖行。

测试失败后仍尝试导出和上传已有证据；依赖安装失败等未产生数据的情况，不能据此宣称完成覆盖率测量。
报告只使用隔离测试数据。真实设备、儿童数据和模型密钥不得放入 CI 产物。

## 重点用例与复现

```powershell
python -m pip install -r tests/requirements.txt
python -m pip install coverage==7.10.7 ruff==0.17.3
python -m coverage run --source=dashboard -m unittest discover -s tests -v
python -m coverage report -m
python scripts/verify_repository.py
python -m ruff check dashboard scripts tests
```

| 风险 | 自动化证据 |
|---|---|
| 一批消息部分失败却改变了已有记录 | `test_dialogue_batch_assignment_is_atomic_and_admin_only` |
| 无效、停用学生或冲突参数触发写入 | `test_batch_assignment_rejects_invalid_inputs_without_writing` |
| 管理员会话被跨站利用 | `test_batch_assignment_requires_csrf_and_same_origin` |
| 旧单条接口失效、重新关联后班级未更新 | `test_single_assignment_and_batch_reassignment_persist` |
| 写盘失败损坏旧数据、留下临时文件 | `test_json_storage.py` 中的失败注入测试 |

测试不是越多越好；新增用例应针对独立的风险或边界。完整用例分布见 [测试计划](TEST_PLAN.md)。
当前静态页面测试不能代替浏览器端到端测试，真机准确率和时延也不由 CI 证明。
PR 中应分别说明自动化结果、手工交互检查和未验证内容，避免只粘贴“测试通过”。
