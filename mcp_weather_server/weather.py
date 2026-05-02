from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from importlib import resources
from typing import Any, AsyncIterator

import httpx
from mcp.server.fastmcp import Context, FastMCP

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


def _load_supported_regions() -> list[str]:
    resource = resources.files(__package__).joinpath("data/supported_regions.json")
    return json.loads(resource.read_text(encoding="utf-8"))


SUPPORTED_REGIONS = _load_supported_regions()


def _json_text(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"))


logger = logging.getLogger("mcp_weather_server.weather")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def _log_event(event: str, **fields: Any) -> None:
    logger.info(_json_text({"event": event, **fields}))


@asynccontextmanager
async def _lifespan(_app: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        _log_event("lifespan.start")
        try:
            yield {"http_client": client}
        finally:
            _log_event("lifespan.stop")


mcp = FastMCP("weather", lifespan=_lifespan)


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


async def _notify_info(ctx: Context | None, message: str) -> None:
    if ctx is not None:
        try:
            await ctx.info(message)
        except Exception:
            pass


def _shared_http_client(ctx: Context | None) -> httpx.AsyncClient | None:
    if ctx is None:
        return None

    try:
        request_context = ctx.fastmcp.request_context
    except Exception:
        return None

    lifespan_context = getattr(request_context, "lifespan_context", None)
    if isinstance(lifespan_context, dict):
        client = lifespan_context.get("http_client")
        if client is not None:
            return client

    return None


@asynccontextmanager
async def _http_client(ctx: Context | None) -> AsyncIterator[httpx.AsyncClient]:
    client = _shared_http_client(ctx)
    if client is not None:
        yield client
        return

    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


async def _request_json(
    url: str,
    params: dict[str, Any],
    *,
    ctx: Context | None = None,
) -> dict[str, Any]:
    async with _http_client(ctx) as client:
        response = await client.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        payload = response.json()

    return payload if isinstance(payload, dict) else {}


async def _resolve_location(location_id: int, ctx: Context | None = None) -> dict[str, Any] | None:
    payload = await _request_json(GEOCODING_API_BASE, {"id": location_id}, ctx=ctx)

    location = _first_location(payload)
    if not location:
        return None

    return _normalize_location(location)


async def _fetch_forecast(
    latitude: float,
    longitude: float,
    days: int,
    *,
    ctx: Context | None = None,
) -> dict[str, Any]:
    return await _request_json(
        FORECAST_API_BASE,
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": FORECAST_DAILY_FIELDS,
            "forecast_days": days,
            "timezone": "auto",
        },
        ctx=ctx,
    )


async def _fetch_current(
    latitude: float,
    longitude: float,
    *,
    ctx: Context | None = None,
) -> dict[str, Any]:
    return await _request_json(
        FORECAST_API_BASE,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": CURRENT_FIELDS,
            "timezone": "auto",
        },
        ctx=ctx,
    )


@mcp.tool()
async def search_location(query: str, ctx: Context | None = None) -> list[dict[str, Any]] | str:
    """Resolve an ambiguous place name to canonical location IDs.
    Use this BEFORE get_forecast or get_current. Returns matches with
    state/country/coords for disambiguation.
    Do NOT use to retrieve weather — only resolves names to IDs."""
    if not query.strip():
        return "Please provide a search query."

    try:
        cleaned_query = query.strip()
        _log_event("search_location.request", query=cleaned_query)
        await _notify_info(ctx, f"searching locations for {cleaned_query}")
        payload = await _request_json(
            GEOCODING_SEARCH_API_BASE,
            {"name": cleaned_query, "count": 10, "language": "en"},
            ctx=ctx,
        )
    except Exception:
        logger.exception(_json_text({"event": "search_location.error", "query": query.strip()}))
        return "Unable to search locations."

    results = payload.get("results", []) if isinstance(payload, dict) else []
    matches = []
    for location in results:
        if not isinstance(location, dict):
            continue
        matches.append(_normalize_location(location, id_key="id"))

    return matches


@mcp.tool()
async def get_forecast(location_id: int, days: int = 5, ctx: Context | None = None) -> dict[str, Any] | str:
    """Return a 1-7 day forecast for a known location_id.
    Requires a location_id from search_location. For current
    conditions, use get_current instead."""
    if not isinstance(location_id, int) or location_id <= 0:
        return "Please provide a valid location id."
    if not isinstance(days, int) or days < 1 or days > 7:
        return "Please provide between 1 and 7 forecast days."

    try:
        _log_event("get_forecast.request", location_id=location_id, days=days)
        await _notify_info(ctx, "resolving location for forecast")
        location = await _resolve_location(location_id, ctx=ctx)
        if not location:
            _log_event("get_forecast.location_missing", location_id=location_id)
            return "Location not found."

        await _notify_info(ctx, "fetching forecast")
        forecast_data = await _fetch_forecast(
            location["latitude"],
            location["longitude"],
            days,
            ctx=ctx,
        )
    except Exception:
        logger.exception(
            _json_text({"event": "get_forecast.error", "location_id": location_id, "days": days})
        )
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
async def get_current(location_id: int, ctx: Context | None = None) -> dict[str, Any] | str:
    """Return weather conditions RIGHT NOW for a known location_id.
    Requires a location_id from search_location. For future
    conditions, use get_forecast instead."""
    if not isinstance(location_id, int) or location_id <= 0:
        return "Please provide a valid location id."

    try:
        _log_event("get_current.request", location_id=location_id)
        await _notify_info(ctx, "resolving location for current conditions")
        location = await _resolve_location(location_id, ctx=ctx)
        if not location:
            _log_event("get_current.location_missing", location_id=location_id)
            return "Location not found."

        await _notify_info(ctx, "fetching current conditions")
        current_data = await _fetch_current(location["latitude"], location["longitude"], ctx=ctx)
    except Exception:
        logger.exception(_json_text({"event": "get_current.error", "location_id": location_id}))
        return "Unable to fetch current conditions."

    current = current_data.get("current", {}) if isinstance(current_data, dict) else {}
    if not current:
        return "Unable to fetch current conditions."

    return {
        "location": location,
        "current": current,
        "units": (current_data.get("current_units") if isinstance(current_data, dict) else {}),
    }


@mcp.prompt(description="Plan a trip weather briefing for a destination and trip length.")
def trip_weather_briefing(destination: str, days: int) -> str:
    return (
        f"Prepare a weather briefing for a trip to {destination} lasting {days} days.\n"
        f"1. Call search_location with {destination!r}.\n"
        "2. If there are multiple matches, choose the best match and note the assumption.\n"
        f"3. Call get_forecast with the selected location id and {days} days.\n"
        "4. Summarize the weather and what to pack."
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
