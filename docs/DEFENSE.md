# 课设答辩交付索引

核对基线为 `main` 的 `934375e`，验收结果包括本次答辩修订。
浏览器功能和目录讲解以 [项目仓库](https://github.com/2796923149akeman-jpg/tongyu-zhishu) 为入口。
提交前在退出 GitHub 登录的浏览器窗口中核对 README、PR、Actions 和演示 Release 是否能打开。现场另备一份演示视频和脱敏截图。

## 15 分钟展示顺序

| 时间 | 内容 | 要展示的材料 |
| --- | --- | --- |
| 0:00–4:00 | 项目场景、架构和重构 | 用 [架构与 UML](ARCHITECTURE.md) 解释告警如何从页面提示走到可处置的事件，再用 [同输入对照](REFACTORING.md#4-同一输入的事件能力对照) 给出结果 |
| 4:00–9:00 | 实机演示 | 打开监控，触发告警并核对事件编号，处置后切换家长账号。使用 ESP32 做一轮语音问答并核对网页文字。设备异常时按 [演示脚本](DEMO_SCRIPT.md) 切模拟方案 |
| 9:00–14:00 | 仓库目录与交付 | 从根目录介绍 `dashboard/`、`xiaozhi-server/`、`tests/`、`docs/`、`scripts/`、`.github/workflows/`。展示 [PR #7](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/7)、[验证记录](VALIDATION.md) 和 [团队贡献](TEAM.md) |
| 14:00–15:00 | 经验分享与答问 | 说明一个 AI 协助开发的实例和验收方法，再说明设备与软件的验证边界 |

## 评分点与证据

### Git 仓库

| 编号 | 复查结果 | 证据或剩余工作 |
| --- | --- | --- |
| 1 | 已有代码风格和贡献指南 | [代码风格](CODE_STYLE.md)、[贡献指南](../CONTRIBUTING.md) |
| 2 | 已有实际分支、Issue 和 PR | [Issue #4](https://github.com/2796923149akeman-jpg/tongyu-zhishu/issues/4) 与 [PR #7](https://github.com/2796923149akeman-jpg/tongyu-zhishu/pull/7) 可对照。Issue 草案另行标注 |
| 3 | 已有忽略规则和提交候选检查 | [忽略规则](../.gitignore)、[仓库检查](../scripts/verify_repository.py) |
| 4 | 已有许可证和供应链清单 | [项目许可](../LICENSE)、[上游来源](../THIRD_PARTY.md)、[供应链](SUPPLY_CHAIN.md) |
| 5 | 常用参数可覆盖，仍有设备默认值 | [配置说明](CONFIGURATION.md) 明确 `RDK_BASE` 等覆盖项。部署时填写实际设备地址 |
| 6 | 有英文提交规范，历史标题格式有差异 | [提交规范](../CONTRIBUTING.md#3-提交信息规范) |
| 7 | 多数近期任务有独立提交，早期有合并交付 | 用本次 PR 的分项提交展示粒度，历史保留供追溯 |
| 8 | 已有提交前检查和 CI lint 配置 | [钩子配置](../.pre-commit-config.yaml)、[CI](../.github/workflows/checks.yml)。贡献者需在本机安装钩子 |
| 9 | 页面与 API 分离，五类业务记录走独立仓储 | [架构说明](ARCHITECTURE.md) |
| 10 | 已有部署与模拟演示脚本 | [部署说明](DEPLOY.md)。本次验证 Windows 下通过 `demo.ps1 -NoBrowser` 启动两个服务并完成告警请求 |

### 文档与实验

| 编号 | 复查结果 | 证据或剩余工作 |
| --- | --- | --- |
| 1 | 已有分角色用户手册 | [用户手册](USER_GUIDE.md) |
| 2 | 已有 UML、结构指标和同输入验证 | [架构](ARCHITECTURE.md)、[设计模式](DESIGN_PATTERNS.md)、[重构对照](REFACTORING.md) |
| 3 | 已有本地基准、模拟业务对照和真机连通抽查 | [实验结果](EXPERIMENTS.md)、[真机记录](DEVICE_VALIDATION.md)。真机记录证明接口连通与数据可读。RDK 视觉识别准确率、STM32 测量误差和真实告警到页面的时延仍待实测 |
| 4 | 已记录软件、模拟环境及真机联调条件 | [环境说明](ENVIRONMENT.md)、[历史联调与当日抽查](DEVICE_VALIDATION.md)。演示时注明所引用的记录版本和范围 |
| 5 | 已有自动化用例和启动回归 | [测试计划](TEST_PLAN.md)、[本次验证](VALIDATION.md) |
| 6 | 已有安全设计和越权验证 | [安全设计](SECURITY.md)。本次模拟验证中，同一事件详情和授权截图对绑定家长返回 `200`，对另一家长返回 `404` |
| 7 | 已提供 42 秒系统演示视频，使用模拟 RDK 和合成数据 | [下载演示视频](https://github.com/2796923149akeman-jpg/tongyu-zhishu/releases/tag/course-demo) · [现场演示流程](DEMO_SCRIPT.md) |

### 团队与经验

| 编号 | 复查结果 | 证据或剩余工作 |
| --- | --- | --- |
| 1 | 有可复现的工作量度量 | [团队记录](TEAM.md) 固定了提交范围，分别列全量和剔除初始导入的结果 |
| 2 | 已有绩效建议比例和说明 | 三位成员根据真实联调、测试、设计和评审记录确认最终分配 |
| 3 | 三人都有作者提交和独立交付 | [团队记录](TEAM.md) 的计数和代表性 PR |
| 4 | 已列可核验的测试、设计和文档贡献 | 每人仍需确认本人展示的交付证据。未留下记录的联调和评审可用当天验收记录补充 |

## AI 协助开发实例

本次用 Codex 对照评分条款和 Git 历史，找到 F5 与一键启动路径遗漏环境监控的问题。
修复后增加真实启动入口的回归用例，在隔离的模拟 RDK 返回超限读数时，确认没有浏览器请求也能产生环境事件。
同一轮核对还发现团队表将合并记录及初始上游导入混入工作量，改为按固定版本重跑度量。
答辩时可展示启动回归和度量命令作为验收证据。
