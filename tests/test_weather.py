"""Weather lookup regression tests; no API credentials or external requests."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "weather_under_test", ROOT / "xiaozhi-server/core/utils/open_meteo_weather.py"
)
weather = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weather)

DATA = {
    "timezone": "Asia/Shanghai",
    "current": {"time": "2026-10-23T16:00", "temperature_2m": 19, "weather_code": 3},
    "daily": {
        "time": ["2026-10-23", "2026-10-24"], "weather_code": [61, 0],
        "temperature_2m_min": [15, 16], "temperature_2m_max": [20, 24],
        "precipitation_probability_max": [40, 0],
    },
}
CONFIG = {"default_location": "长沙", "latitude": 28.2282, "longitude": 112.9388}


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    def test_report_distinguishes_dates_and_current_temperature(self):
        report = weather.format_report(DATA, "长沙")
        self.assertIn("气温 19℃", report)
        self.assertIn("2026-10-24：晴，16~24℃，降水概率 0%", report)
        self.assertIn("Open-Meteo", report)

    def test_missing_data_is_not_invented(self):
        bad = copy.deepcopy(DATA)
        bad["current"]["temperature_2m"] = None
        with self.assertRaises(ValueError):
            weather.format_report(bad, "长沙")
        bad = copy.deepcopy(DATA)
        bad["daily"]["weather_code"] = []
        with self.assertRaises(ValueError):
            weather.format_report(bad, "长沙")

    async def test_default_city_uses_configured_coordinates_without_geocoding(self):
        requests = []

        def handle(request):
            requests.append(request)
            self.assertEqual(request.url.host, "api.open-meteo.com")
            self.assertEqual(request.url.params["latitude"], "28.2282")
            self.assertEqual(request.url.params["longitude"], "112.9388")
            self.assertNotIn("authorization", request.headers)
            return httpx.Response(200, json=DATA)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        with patch.object(weather.httpx, "AsyncClient", return_value=client):
            report = await weather.fetch_report("长沙市", CONFIG)
        self.assertEqual(len(requests), 1)
        self.assertIn("查询地点：长沙", report)

    async def test_unknown_city_does_not_silently_return_changsha(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": []})
        ))
        with patch.object(weather.httpx, "AsyncClient", return_value=client):
            with self.assertRaisesRegex(ValueError, "City not found"):
                await weather.fetch_report("不存在的城市", CONFIG)

    async def test_http_failure_is_not_a_weather_report(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(503, json={"error": True})
        ))
        with patch.object(weather.httpx, "AsyncClient", return_value=client):
            with self.assertRaises(httpx.HTTPStatusError):
                await weather.fetch_report("长沙", CONFIG)


if __name__ == "__main__":
    unittest.main()
