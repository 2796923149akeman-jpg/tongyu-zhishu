# 童域智枢：基础监控与对话测试

本项目包含两个独立运行的 Python 服务：基础监控网页，以及基于小智开源后端的 ESP32 语音对话服务。2026-10-17 整理为本仓库初始版本。

## 目录

```text
dashboard/          指定的基础监控网页、只读对话测试页
xiaozhi-server/      官方小智后端，加上后台消息转发
scripts/            初始化、运行环境与提交文件检查
tests/              不依赖硬件或付费 API 的隔离测试
docs/               开发流程、来源和验证记录
```

监控页使用 RDK 的 `/video_feed`、`/alert_status`、`/api/iot_payload`，显示真实设备数据。对话页显示 ESP32 已识别的用户文字和机器人即将播放的回复句子，不在网页重复调用模型。

## 当前电脑运行

使用 Windows **CMD / Anaconda Prompt**；以下 `set` 和 `cd /d` 是 CMD 语法。原有工程与本工程端口相同，先停止旧目录运行的服务。

先运行小智：

```bat
cd /d D:\ESP32\tongyu-zhishu-v1\xiaozhi-server
conda activate xiaozhi-esp32-server
python app.py
```

再在另一个终端运行网页：

```bat
cd /d D:\ESP32\tongyu-zhishu-v1\dashboard
conda activate xiaozhi-esp32-server
set RDK_BASE=http://192.168.43.54:5000
python server.py
```

- 基础监控：<http://127.0.0.1:8088/>
- 对话测试：<http://127.0.0.1:8088/chat>
- ESP32 连接电脑局域网地址：`ws://电脑IP:8000/xiaozhi/v1/`；HTTP/OTA 端口为 8003。

网页启动后再对 ESP32 说话。之前的消息不会补发。回复按语音句子显示，保留最近 200 条，网页服务重启后清空。此处的“网页服务已连接”不表示 ESP32 或模型 API 已连接。对话测试页限服务电脑本机访问，监控页仍可在局域网查看。

当前电脑已经复制现有私有配置与 ASR/VAD 模型，它们都被 Git 忽略。默认使用现有 DeepSeek 对话接口和儿童陪伴提示词；真实 API Key 不上传。

## 模型与提示词

修改 `xiaozhi-server/data/.config.yaml` 中 `LLM.DeepSeekLLM` 的接口、`model_name`、`api_key` 及顶层 `prompt`，然后重启 `app.py` 生效。当前版本没有网页修改模型功能。

`config.yaml` 是通用默认配置，`data/.config.yaml` 是本机覆盖配置；不依赖官方在线智控台。不要修改公开模板填写真实密钥。

## 队友首次配置

1. 克隆仓库并创建 Python 3.10 环境，安装 `pip install -r requirements.txt`，安装 FFmpeg 并加入 PATH。依赖继承自已有小智版本，全新环境安装尚未实测。
2. 在仓库根目录运行 `python scripts/setup_local.py`，填写本机 `data/.config.yaml` 中的 API Key。模型名称、接口和提示词模板已备好。
3. 准备 SenseVoiceSmall 和 Silero 完整模型目录到 `xiaozhi-server/models`，参考 [模型文件清单](docs/model-files.json)。可从当前可运行电脑取得，模型不进入 Git。
4. 运行 `python scripts/check_runtime.py` 检查环境，然后分别启动两个服务。

仅开发网页时只需要 Python 标准库，不需要安装小智的全部依赖。PowerShell 设置 RDK 地址应使用 `$env:RDK_BASE="http://192.168.43.54:5000"`。

## 检查与协作

```bat
python -m unittest discover -s tests -v
python scripts/verify_repository.py
```

只有执行 `git commit` 才产生记录，保存文件不会自动提交；执行 `git push` 后 GitHub 才能看到。三人分别使用自己的账号与开发分支，按真实任务提交，详见 [协作说明](docs/DEVELOPMENT.md)。

上游源码归属和修改范围见 [第三方来源](THIRD_PARTY.md)，测试边界见 [验证记录](docs/VALIDATION.md)。本初始版本是对既有基础监控代码及官方后端的整理，不代表此前开发历史已被 Git 记录。
