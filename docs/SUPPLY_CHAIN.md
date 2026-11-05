# 开源供应链说明

更新日期：2026-11-05

本文档记录仓库使用的开源组件、来源、版本、许可证与修改范围，配合
[THIRD_PARTY.md](../THIRD_PARTY.md) 和 [LICENSE](../LICENSE) 使用。

## 1. 组件清单

| 组件 | 来源 / 版本 | 许可证 | 使用方式 | 团队修改 |
|---|---|---|---|---|
| xiaozhi-esp32-server | <https://github.com/xinnan-tech/xiaozhi-esp32-server>，commit `c5b64c3` 的 `main/xiaozhi-server` | MIT（保留 `xiaozhi-server/LICENSE`） | ESP32 语音会话、ASR/TTS/LLM 接入 | 增加 `core/utils/dialogue_monitor.py`；在 `sendAudioHandle.py` 的 STT/TTS 发送处调用转发；配置模板脱敏 |
| xiaozhi-esp32-server 内置提示音 | 同上 | 随上游（MIT） | 唤醒词、绑定提示等 WAV 资源 | 未修改 |
| cnsenti / cntext | <https://github.com/hiDaDeng/cnsenti>、<https://github.com/hiDaDeng/cntext> | MIT | 情绪分类设计参考 | 仅参考分类思路，未复制词典；`dashboard/emotion_lexicon.json` 为自建词条 |
| SenseVoiceSmall | <https://huggingface.co/FunAudioLLM/SenseVoiceSmall> | 以模型发布方许可为准 | 本地语音识别模型 | 模型不随 Git 分发，见 `docs/model-files.json` |
| Silero VAD | <https://github.com/snakers4/silero-vad> | MIT（以发布方为准） | 语音活动检测 ONNX/JIT | 模型不随 Git 分发 |
| Open-Meteo | <https://open-meteo.com/> | 数据 CC BY 4.0（以站点条款为准） | 天气工具函数 | 通过 `xiaozhi-server/core/utils/open_meteo_weather.py` 调用，需保留署名 |
| PyYAML | PyPI，`6.0.3` | MIT | 读写小智模型 YAML 配置 | 未修改 |
| httpx | PyPI，`0.28.1` | BSD-3-Clause | 测试中的 HTTP 客户端 | 未修改 |
| Ultralytics / PyTorch / torchvision / OpenCV / NumPy / lap / polars | PyPI，版本见 `scripts/requirements-person-type.txt` | AGPL-3.0（Ultralytics）、BSD 等（以各项目为准） | 可选人物估算演示 | 仅在本地可选启用，默认关闭；不随仓库分发模型权重 |
| FFmpeg / libopus | 系统包 | LGPL/GPL（以发行版为准） | 语音环境音频编解码 | 未修改 |

> Ultralytics 使用 AGPL-3.0：人物估算仅作为课程演示的可选本地功能，默认关闭；
> 如对外分发或商用，需要单独评估 AGPL 义务或替换实现。

## 2. 依赖锁定

- 网页主体只使用 Python 标准库 + `PyYAML==6.0.3`（`dashboard/requirements.txt`）。
- 测试依赖 `httpx==0.28.1`（`tests/requirements.txt`）。
- 语音服务依赖见 `xiaozhi-server/requirements.txt`（上游锁定版本）。
- 人物估算为可选依赖，未安装时相关接口返回 400/关闭状态。

## 3. 许可证策略

- 团队新增代码：MIT（见根目录 `LICENSE`）。
- 上游 xiaozhi 代码：保留 MIT 与原版权声明，不改为团队许可证。
- 小智上游内置提示音随源码分发，保留在 `xiaozhi-server/config/assets/`，沿用上游许可说明。
- 模型权重和第三方数据集遵循各自发布方许可，由部署者按需获取，仓库不随源码分发这些文件。运行时生成的音频保存在本机。
- 公开发布前若引入新的第三方组件，需在本文档补充来源、版本和许可证。

## 4. 合规检查

- `scripts/verify_repository.py` 在 CI 中检查敏感文件、超大文件和硬编码凭据。
- 运行数据、密钥、模型和截图运行时目录均被 `.gitignore` 排除。
- 仓库不包含真实儿童照片、真实 API Key 或完整对话原文。
