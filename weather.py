from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

GEOCODING_API_BASE = "https://geocoding-api.open-meteo.com/v1/get"
FORECAST_API_BASE = "https://api.open-meteo.com/v1/forecast"

FORECAST_DAILY_FIELDS = "temperature_2m_max,temperature_2m_min"


def _first_location(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict) and "results" in payload:
        results = payload.get("results") or []
        if results:
            item = results[0]
            return item if isinstance(item, dict) else None
        return None

    return payload if isinstance(payload, dict) else None


def _normalize_location(location: dict[str, Any]) -> dict[str, Any]:
    return {
        "location_id": location.get("id", location.get("location_id")),
        "name": location.get("name"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "timezone": location.get("timezone"),
        "country": location.get("country"),
        "admin1": location.get("admin1"),
        "feature_code": location.get("feature_code"),
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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
