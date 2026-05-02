from __future__ import annotations

import json
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
UNITS_CONFIG = {"temperature": "celsius", "wind": "kmh"}
SUPPORTED_REGIONS = ["BR", "AR", "UY", "PY"]


def _json_text(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"))


@mcp.resource("config://units")
def units_config() -> str:
    """Read-only weather unit defaults."""
    return _json_text(UNITS_CONFIG)


@mcp.resource("config://supported_regions")
def supported_regions_config() -> str:
    """Read-only list of supported regions."""
    return _json_text(SUPPORTED_REGIONS)


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
    """Resolve an ambiguous place name to canonical location IDs.
    Use this BEFORE get_forecast or get_current. Returns matches with
    state/country/coords for disambiguation.
    Do NOT use to retrieve weather — only resolves names to IDs."""
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
    """Return a 1-7 day forecast for a known location_id.
    Requires a location_id from search_location. For current
    conditions, use get_current instead."""
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
    """Return weather conditions RIGHT NOW for a known location_id.
    Requires a location_id from search_location. For future
    conditions, use get_forecast instead."""
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

    return {
        "location": location,
        "current": current,
        "units": (current_data.get("current_units") if isinstance(current_data, dict) else {}),
    }


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
