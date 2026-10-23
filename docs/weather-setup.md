# 长沙天气与 DeepSeek 模型

本机的 `xiaozhi-server/data/.config.yaml` 使用 `deepseek-v4-pro`，并启用
`Intent: function_call`。语音场景关闭 DeepSeek 的深度思考，模型仍可调用天气工具。
模型调用按 DeepSeek 账户计费，Pro 的单价高于 Flash。

仓库的默认配置已经包含以下天气设置；如果需要更换默认城市，再在本地配置中覆盖：

```yaml
plugins:
  get_weather:
    provider: open_meteo
    default_location: 长沙
    prefer_default_location: true
    latitude: 28.2282
    longitude: 112.9388
Intent:
  function_call:
    type: function_call
    functions:
      - get_weather
```

Open-Meteo 提供数值天气模型估算及七天预报，不代表现场传感器实测。
工具结果保留来源、当地时间、每日日期，缓存十分钟。网络、城市查询或数据异常时
会告知查询失败，不会退回模型猜测天气。默认长沙使用配置的坐标；显式指定其他城市时
使用地名查询，遇到同名地点需确认返回的位置。保留原有和风天气实现供其他配置使用。

Open-Meteo 公共接口适用于非商业用途；商业部署需遵循其授权和服务方案。
来源：[Open-Meteo](https://open-meteo.com/)、[接口文档](https://open-meteo.com/en/docs)、
[DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)。

改配置后，停止并重新启动小智服务；网页服务按原来的方式运行。
先问“今天天气怎么样”，再问“长沙明天会下雨吗”。终端应出现天气工具调用，随后生成语音。
