"""Live forecast data from Open-Meteo; no model or weather credentials needed."""
import asyncio
import httpx


WMO_TEXT = {
    0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴", 45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "强毛毛雨", 56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "米雪",
    80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "阵雪", 86: "强阵雪",
    95: "雷阵雨", 96: "雷雨伴小冰雹", 99: "雷雨伴大冰雹",
}


def format_report(data, location):
    current = data.get("current") or {}
    if not current.get("time") or current.get("temperature_2m") is None:
        raise ValueError("Weather response has no current temperature/time")
    lines = [
        f"查询地点：{location}；数据来源：Open-Meteo（数值天气模型估算/预报）。",
        f"当地数据时间：{current['time']}；时区：{data.get('timezone', 'Asia/Shanghai')}。",
        f"当前：{WMO_TEXT.get(current.get('weather_code'), '天气状况未知')}，"
        f"气温 {current['temperature_2m']}℃。",
        "未来7天预报（按日期回答，不能把当前温度当作全天最高温）：",
    ]
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    fields = [daily.get(k) or [] for k in (
        "weather_code", "temperature_2m_min", "temperature_2m_max", "precipitation_probability_max"
    )]
    if not dates or any(len(values) != len(dates) for values in fields):
        raise ValueError("Weather response has incomplete daily forecast")
    for date, code, low, high, rain in zip(dates, *fields):
        temp = f"{low}~{high}℃" if low is not None and high is not None else "温度数据缺失"
        chance = f"{rain}%" if rain is not None else "未知"
        lines.append(f"{date}：{WMO_TEXT.get(code, '天气状况未知')}，{temp}，降水概率 {chance}。")
    lines.append("天气预报会变化；只能依据上述数据回答，不要编造实时观测或天气预警。")
    return "\n".join(lines)


async def _fetch(location, config):
    default = config.get("default_location", "长沙")
    async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0)) as client:
        if location.removesuffix("市") == default.removesuffix("市") and all(
            config.get(k) is not None for k in ("latitude", "longitude")
        ):
            latitude, longitude = config["latitude"], config["longitude"]
            label = default
        else:
            response = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 5, "language": "zh", "format": "json"},
            )
            response.raise_for_status()
            places = response.json().get("results") or []
            if not places:
                raise ValueError("City not found")
            place = next((p for p in places if p.get("country_code") == "CN"), places[0])
            latitude, longitude = place["latitude"], place["longitude"]
            label = " ".join(str(place[k]) for k in ("country", "admin1", "name") if place.get(k))
        response = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude, "longitude": longitude,
                "current": "temperature_2m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto", "forecast_days": 7,
            },
        )
        response.raise_for_status()
        return format_report(response.json(), label)


async def fetch_report(location, config):
    # Prompt context waits for at most ten seconds; keep the full lookup bounded.
    return await asyncio.wait_for(_fetch(location, config), timeout=8.0)
