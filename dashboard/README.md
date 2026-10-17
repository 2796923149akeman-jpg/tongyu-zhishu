# V1 基础监控看板

该版本作为课程项目的 Git 历史起点，完成电脑端对 RDK 真实数据的集中显示，并增加一个只读 ESP32 对话测试页。

## 数据接口

- 画面：RDK `web_fall.py` 的 `/video_feed`
- 行为状态：RDK `web_fall.py` 的 `/alert_status`
- 温度和环境数据：RDK `web_fall.py` 的 `/api/iot_payload`

页面不生成模拟温度或空气质量数据；接口缺失的数值显示为 `--`，接口异常通过页面状态栏提示。

## 运行

配置上游数据接口地址后，在 Windows 终端运行：

```bat
cd /d D:\ESP32\tongyu-zhishu-v1\dashboard
conda activate xiaozhi-esp32-server
set RDK_BASE=http://192.168.43.54:5000
python server.py
```

浏览器打开 <http://127.0.0.1:8088>。

本机对话测试页为 <http://127.0.0.1:8088/chat>。小智服务启动后，对 ESP32 说话即可查看识别文字和回复句子；保留最近 200 条，不保存历史，也不在网页单独调用模型。

如果 RDK 地址变化，只修改 `RDK_BASE`，不需要修改代码。
