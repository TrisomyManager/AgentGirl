"""Open-Meteo weather lookup (no API key).

Uses the free Open-Meteo public API: geocoding + current weather.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger("action_executor.weather_open_meteo")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _normalize_location(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "北京"
    # Drop common Chinese filler so geocoding still works.
    for noise in ("天气", "气温", "怎么样", "如何", "查一下", "帮我看看"):
        s = s.replace(noise, "")
    return s.strip() or "北京"


async def fetch_current_weather(location: str) -> tuple[bool, str, dict[str, Any]]:
    """Return (ok, user_message, data_dict).

    ``data_dict`` always includes ``source`` (``open_meteo`` or ``error``).
    """
    loc = _normalize_location(location)
    timeout = httpx.Timeout(8.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            geo = await client.get(
                GEOCODE_URL,
                params={"name": loc, "count": 1, "language": "zh", "format": "json"},
            )
            geo.raise_for_status()
            geo_json = geo.json()
        except Exception as exc:
            logger.warning("weather.geocode_failed", location=loc, error=str(exc))
            return (
                False,
                "天气服务暂时连不上，稍后再试一次好吗？",
                {"source": "error", "location_query": loc, "error": str(exc)},
            )

        results = geo_json.get("results") or []
        if not results:
            return (
                True,
                f"我没找到「{loc}」对应的城市坐标，换个更具体的地名试试？",
                {
                    "source": "open_meteo",
                    "location_query": loc,
                    "resolved": False,
                },
            )

        r0 = results[0]
        lat, lon = r0.get("latitude"), r0.get("longitude")
        name = r0.get("name") or loc
        country = r0.get("country") or ""
        admin1 = r0.get("admin1") or ""
        label = name
        if admin1:
            label = f"{name}（{admin1}）"
        if country and country not in label:
            label = f"{label}，{country}"

        try:
            wx = await client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            wx.raise_for_status()
            wx_json = wx.json()
        except Exception as exc:
            logger.warning("weather.forecast_failed", location=label, error=str(exc))
            return (
                False,
                f"查到「{label}」了，但取实时天气失败，稍后再试？",
                {
                    "source": "error",
                    "location_query": loc,
                    "resolved_name": label,
                    "error": str(exc),
                },
            )

        cur = wx_json.get("current") or {}
        temp = cur.get("temperature_2m")
        rh = cur.get("relative_humidity_2m")
        code = cur.get("weather_code")
        wind = cur.get("wind_speed_10m")

        desc = _weather_code_zh(code)
        parts = [f"「{label}」现在{desc}"]
        if temp is not None:
            parts.append(f"气温约 {temp}°C")
        if rh is not None:
            parts.append(f"相对湿度约 {int(rh)}%")
        if wind is not None:
            parts.append(f"10 米风速约 {wind} m/s")
        msg = "，".join(parts) + "。（数据来自 Open-Meteo 公开接口）"

        return (
            True,
            msg,
            {
                "source": "open_meteo",
                "location_query": loc,
                "resolved_name": label,
                "latitude": lat,
                "longitude": lon,
                "temperature_2m": temp,
                "relative_humidity_2m": rh,
                "weather_code": code,
                "wind_speed_10m": wind,
            },
        )


def _weather_code_zh(code: int | None) -> str:
    """WMO weather interpretation string (short Chinese)."""
    if code is None:
        return "天气状况未知"
    table: dict[int, str] = {
        0: "晴朗",
        1: "大部晴朗",
        2: "多云间晴",
        3: "阴云密布",
        45: "有雾",
        48: "有雾凇/沉积雾",
        51: "小毛毛雨",
        53: "中毛毛雨",
        55: "大毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        80: "阵雨",
        81: "强阵雨",
        82: "暴雨阵雨",
        95: "雷暴",
        96: "雷暴伴冰雹",
        99: "强雷暴伴冰雹",
    }
    return table.get(int(code), f"天气代码 {code}")
