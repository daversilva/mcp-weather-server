from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

GEOCODING_API_BASE = "https://geocoding-api.open-meteo.com/v1/get"
GEOCODING_SEARCH_API_BASE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API_BASE = "https://api.open-meteo.com/v1/forecast"

FORECAST_DAILY_FIELDS = "temperature_2m_max,temperature_2m_min"
CURRENT_FIELDS = ",".join(
    [
        "temperature_2m",
        "apparent_temperature",
        "relative_humidity_2m",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "weather_code",
    ]
)

WMO_CONDITIONS: dict[int, str] = {
    0: "clear",
    1: "partly_cloudy",
    2: "partly_cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "freezing_drizzle",
    57: "freezing_drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "freezing_rain",
    67: "freezing_rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow_grains",
    80: "rain_showers",
    81: "rain_showers",
    82: "rain_showers",
    85: "snow_showers",
    86: "snow_showers",
    95: "thunderstorm",
    96: "thunderstorm_hail",
    99: "thunderstorm_hail",
}


def _first_location(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict) and "results" in payload:
        results = payload.get("results") or []
        if results:
            item = results[0]
            return item if isinstance(item, dict) else None
        return None

    return payload if isinstance(payload, dict) else None


def _normalize_location(
    location: dict[str, Any],
    *,
    id_key: str = "location_id",
) -> dict[str, Any]:
    return {
        id_key: location.get("id", location.get("location_id")),
        "name": location.get("name"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "timezone": location.get("timezone"),
        "country": location.get("country"),
        "admin1": location.get("admin1"),
        "feature_code": location.get("feature_code"),
    }


def _normalize_current(current: dict[str, Any]) -> dict[str, Any] | None:
    observed_at = current.get("time")
    temp_c = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    wind_kmh = current.get("wind_speed_10m")
    weather_code = current.get("weather_code")

    required_values = [observed_at, temp_c, humidity, wind_kmh, weather_code]
    if any(value is None for value in required_values):
        return None

    condition = WMO_CONDITIONS.get(weather_code, "unknown")
    return {
        "temp_c": temp_c,
        "humidity": humidity,
        "wind_kmh": wind_kmh,
        "condition": condition,
        "observed_at": observed_at,
    }


async def _resolve_location(location_id: int) -> dict[str, Any] | None:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GEOCODING_API_BASE,
            params={"id": location_id},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()

    location = _first_location(payload)
    if not location:
        return None

    return _normalize_location(location)


async def _fetch_forecast(latitude: float, longitude: float, days: int) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            FORECAST_API_BASE,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": FORECAST_DAILY_FIELDS,
                "forecast_days": days,
                "timezone": "auto",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def _fetch_current(latitude: float, longitude: float) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            FORECAST_API_BASE,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": CURRENT_FIELDS,
                "timezone": "auto",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def search_location(query: str) -> list[dict[str, Any]] | str:
    if not query.strip():
        return "Please provide a search query."

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GEOCODING_SEARCH_API_BASE,
                params={"name": query.strip(), "count": 10, "language": "en"},
                timeout=30.0,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return "Unable to search locations."

    results = payload.get("results", []) if isinstance(payload, dict) else []
    matches = []
    for location in results:
        if not isinstance(location, dict):
            continue
        matches.append(_normalize_location(location, id_key="id"))

    return matches


@mcp.tool()
async def get_forecast(location_id: int, days: int = 5) -> dict[str, Any] | str:
    if not isinstance(location_id, int) or location_id <= 0:
        return "Please provide a valid location id."
    if not isinstance(days, int) or days < 1 or days > 7:
        return "Please provide between 1 and 7 forecast days."

    try:
        location = await _resolve_location(location_id)
        if not location:
            return "Location not found."

        forecast_data = await _fetch_forecast(
            location["latitude"],
            location["longitude"],
            days,
        )
    except Exception:
        return "Unable to fetch forecast data."

    daily = forecast_data.get("daily", {}) if isinstance(forecast_data, dict) else {}
    times = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])

    if not times or not max_temps or not min_temps:
        return "Unable to fetch forecast data."

    days_payload = []
    for date, max_temp, min_temp in zip(times[:days], max_temps[:days], min_temps[:days]):
        days_payload.append(
            {
                "date": date,
                "temperature_2m_max": max_temp,
                "temperature_2m_min": min_temp,
            }
        )

    return {
        "location": location,
        "days": days_payload,
        "units": (forecast_data.get("daily_units") if isinstance(forecast_data, dict) else {}),
    }


@mcp.tool()
async def get_current(location_id: int) -> dict[str, Any] | str:
    if not isinstance(location_id, int) or location_id <= 0:
        return "Please provide a valid location id."

    try:
        location = await _resolve_location(location_id)
        if not location:
            return "Location not found."

        current_data = await _fetch_current(location["latitude"], location["longitude"])
    except Exception:
        return "Unable to fetch current conditions."

    current = current_data.get("current", {}) if isinstance(current_data, dict) else {}
    if not current:
        return "Unable to fetch current conditions."

    normalized_current = _normalize_current(current)
    if not normalized_current:
        return "Unable to fetch current conditions."

    return {
        "location": location,
        "current": normalized_current,
        "units": (current_data.get("current_units") if isinstance(current_data, dict) else {}),
    }


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
