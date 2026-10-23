# 第三方来源

小智 Python 后端来自 https://github.com/xinnan-tech/xiaozhi-esp32-server ，导入本地已有版本 `c5b64c3ef0cc5d54e95935937bbd9e54af761c2a` 的 `main/xiaozhi-server`。保留 [MIT 许可证](xiaozhi-server/LICENSE)。没有把上游作者工作计作团队新增功能。

导入官方 Python 代码、提示词模板与内置提示音，不包含 Java/Vue 管理端。后端本次源码修改仅为：增加 `core/utils/dialogue_monitor.py`，并在 `core/handle/sendAudioHandle.py` 的 STT 与 TTS 发送位置调用转发函数。`app.py` 保留此上游版本原文件。

另有配置层调整：默认示例凭据清空；本机模型与儿童陪伴提示词提供脱敏模板；MCP 外部服务默认空；依赖清单中的 `pyyml` 替换为实际使用的 `PyYAML==6.0.3`。

基础监控网页来自本机 `tongyu-zhishu/baseline-dashboard`，之后增加对话入口、情绪线索和会话总结。

情绪类别设计参考 [cnsenti](https://github.com/hiDaDeng/cnsenti) 与 [cntext](https://github.com/hiDaDeng/cntext) 展示的中文情绪分类，两者代码仓库采用 MIT 许可证。本仓库没有复制其内置第三方大词典；`dashboard/emotion_lexicon.json` 的儿童日常词条由本项目独立整理，并在元数据中保留参考链接。

模型权重与第三方 Python 依赖遵循各自许可，模型不随 Git 分发。团队新增代码的整体授权方式由团队决定；小智代码保留其原许可证。
