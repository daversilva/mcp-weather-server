import json
import asyncio

import httpx
import pytest

import weather
from conftest import MockResponse


_REGISTERED_TOOLS = asyncio.run(weather.mcp.list_tools())
_REGISTERED_RESOURCES = asyncio.run(weather.mcp.list_resources())
_REGISTERED_PROMPTS = asyncio.run(weather.mcp.list_prompts())


@pytest.mark.parametrize(
    "tool",
    _REGISTERED_TOOLS,
    ids=[tool.name for tool in _REGISTERED_TOOLS],
)
def test_tool_has_description(tool):
    description = (tool.description or "").strip()
    assert description, f"Tool {tool.name!r} is missing a description"


def test_resources_are_registered():
    assert {str(resource.uri) for resource in _REGISTERED_RESOURCES} >= {
        "config://units",
        "config://supported_regions",
    }


def test_trip_weather_briefing_prompt_is_registered():
    prompt_names = {prompt.name for prompt in _REGISTERED_PROMPTS}

    assert "trip_weather_briefing" in prompt_names


def test_trip_weather_briefing_prompt_has_description_and_arguments():
    prompt = next(prompt for prompt in _REGISTERED_PROMPTS if prompt.name == "trip_weather_briefing")

    assert (prompt.description or "").strip()
    assert [argument.name for argument in prompt.arguments or []] == ["destination", "days"]


@pytest.mark.asyncio
async def test_trip_weather_briefing_prompt_renders_instructions():
    result = await weather.mcp.get_prompt(
        "trip_weather_briefing",
        {"destination": "Goiania", "days": 3},
    )

    assert result.messages[0].role == "user"
    assert "search_location" in result.messages[0].content.text
    assert "get_forecast" in result.messages[0].content.text
    assert "Goiania" in result.messages[0].content.text
    assert "3" in result.messages[0].content.text


@pytest.mark.asyncio
async def test_units_resource_returns_json_text():
    contents = await weather.mcp.read_resource("config://units")

    assert contents[0].content == '{"temperature":"celsius","wind":"kmh"}'


@pytest.mark.asyncio
async def test_supported_regions_resource_returns_json_text():
    contents = await weather.mcp.read_resource("config://supported_regions")

    regions = json.loads(contents[0].content)

    assert regions == weather.SUPPORTED_REGIONS
    assert len(regions) == 249
    for code in {"US", "GB", "ZW"}:
        assert code in regions


def build_location_payload(
    *,
    location_id: int,
    name: str,
    latitude: float,
    longitude: float,
    timezone: str = "America/Sao_Paulo",
    country: str = "Brazil",
    admin1: str = "Goias",
) -> dict:
    return {
        "id": location_id,
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "country": country,
        "admin1": admin1,
        "feature_code": "PPL",
    }


def build_search_response(results: list[dict]) -> MockResponse:
    return MockResponse({"results": results})


def build_forecast_response(
    times: list[str],
    max_temps: list[float],
    min_temps: list[float],
) -> MockResponse:
    return MockResponse(
        {
            "daily": {
                "time": times,
                "temperature_2m_max": max_temps,
                "temperature_2m_min": min_temps,
            },
            "daily_units": {
                "time": "iso8601",
                "temperature_2m_max": "°C",
                "temperature_2m_min": "°C",
            },
        }
    )


def build_current_response() -> MockResponse:
    return MockResponse(
        {
            "current": {
                "time": "2026-05-01T12:00",
                "interval": 900,
                "temperature_2m": 27.3,
                "apparent_temperature": 28.8,
                "relative_humidity_2m": 61,
                "wind_speed_10m": 14.2,
                "wind_direction_10m": 180,
                "wind_gusts_10m": 23.4,
                "weather_code": 1,
            },
            "current_units": {
                "time": "iso8601",
                "interval": "seconds",
                "temperature_2m": "°C",
                "apparent_temperature": "°C",
                "relative_humidity_2m": "%",
                "wind_speed_10m": "km/h",
                "wind_direction_10m": "°",
                "wind_gusts_10m": "km/h",
                "weather_code": "wmo code",
            },
        }
    )


class FakeContext:
    def __init__(self):
        self.info_messages: list[str] = []

    async def info(self, message: str, **extra):
        self.info_messages.append(message)


def build_current_response() -> MockResponse:
    return MockResponse(
        {
            "current": {
                "time": "2026-05-01T12:00",
                "interval": 900,
                "temperature_2m": 27.3,
                "apparent_temperature": 28.8,
                "relative_humidity_2m": 61,
                "wind_speed_10m": 14.2,
                "wind_direction_10m": 180,
                "wind_gusts_10m": 23.4,
                "weather_code": 1,
            },
            "current_units": {
                "time": "iso8601",
                "interval": "seconds",
                "temperature_2m": "°C",
                "apparent_temperature": "°C",
                "relative_humidity_2m": "%",
                "wind_speed_10m": "km/h",
                "wind_direction_10m": "°",
                "wind_gusts_10m": "km/h",
                "weather_code": "wmo code",
            },
        }
    )


@pytest.mark.asyncio
async def test_get_forecast_returns_structured_daily_forecast(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client(
        [
            build_search_response(
                [
                    build_location_payload(
                        location_id=12345,
                        name="Goiania",
                        latitude=-16.6869,
                        longitude=-49.2648,
                    )
                ]
            ),
            build_forecast_response(
                [
                    "2026-05-01",
                    "2026-05-02",
                    "2026-05-03",
                ],
                [30.0, 29.0, 28.0],
                [20.0, 19.0, 18.0],
            ),
        ]
    )

    result = await weather.get_forecast(12345, 3, ctx=ctx)

    assert ctx.info_messages == [
        "resolving location for forecast",
        "fetching forecast",
    ]

    assert result["location"]["location_id"] == 12345
    assert result["location"]["name"] == "Goiania"
    assert result["days"] == [
        {
            "date": "2026-05-01",
            "temperature_2m_max": 30.0,
            "temperature_2m_min": 20.0,
        },
        {
            "date": "2026-05-02",
            "temperature_2m_max": 29.0,
            "temperature_2m_min": 19.0,
        },
        {
            "date": "2026-05-03",
            "temperature_2m_max": 28.0,
            "temperature_2m_min": 18.0,
        },
    ]


@pytest.mark.asyncio
async def test_get_forecast_rejects_invalid_days():
    ctx = FakeContext()
    result = await weather.get_forecast(12345, 8, ctx=ctx)

    assert ctx.info_messages == []
    assert result == "Please provide between 1 and 7 forecast days."


@pytest.mark.asyncio
async def test_get_forecast_reports_missing_location(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client([build_search_response([])])

    result = await weather.get_forecast(999, 3, ctx=ctx)

    assert ctx.info_messages == ["resolving location for forecast"]
    assert result == "Location not found."


@pytest.mark.asyncio
async def test_get_forecast_handles_upstream_errors(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client([httpx.RequestError("network error")])

    result = await weather.get_forecast(12345, 3, ctx=ctx)

    assert ctx.info_messages == ["resolving location for forecast"]
    assert result == "Unable to fetch forecast data."


@pytest.mark.asyncio
async def test_search_location_returns_normalized_matches(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client(
        [
            build_search_response(
                [
                    build_location_payload(
                        location_id=12345,
                        name="Goiania",
                        latitude=-16.6869,
                        longitude=-49.2648,
                    )
                ]
            )
        ]
    )

    result = await weather.search_location("Goiania", ctx=ctx)

    assert ctx.info_messages == ["searching locations for Goiania"]

    assert result == [
        {
            "id": 12345,
            "name": "Goiania",
            "latitude": -16.6869,
            "longitude": -49.2648,
            "timezone": "America/Sao_Paulo",
            "country": "Brazil",
            "admin1": "Goias",
            "feature_code": "PPL",
        }
    ]


@pytest.mark.asyncio
async def test_search_location_rejects_blank_query():
    ctx = FakeContext()
    result = await weather.search_location("   ", ctx=ctx)

    assert ctx.info_messages == []
    assert result == "Please provide a search query."


@pytest.mark.asyncio
async def test_search_location_returns_empty_matches_for_no_results(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client([build_search_response([])])

    result = await weather.search_location("Unknown City", ctx=ctx)

    assert ctx.info_messages == ["searching locations for Unknown City"]

    assert result == []


@pytest.mark.asyncio
async def test_search_location_handles_upstream_errors(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client([httpx.RequestError("network error")])

    result = await weather.search_location("Goiania", ctx=ctx)

    assert ctx.info_messages == ["searching locations for Goiania"]
    assert result == "Unable to search locations."


@pytest.mark.asyncio
async def test_get_current_returns_structured_conditions(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client(
        [
            build_search_response(
                [
                    build_location_payload(
                        location_id=12345,
                        name="Goiania",
                        latitude=-16.6869,
                        longitude=-49.2648,
                    )
                ]
            ),
            build_current_response(),
        ]
    )

    result = await weather.get_current(12345, ctx=ctx)

    assert ctx.info_messages == [
        "resolving location for current conditions",
        "fetching current conditions",
    ]

    assert result["location"]["location_id"] == 12345
    assert result["current"] == {
        "time": "2026-05-01T12:00",
        "interval": 900,
        "temperature_2m": 27.3,
        "apparent_temperature": 28.8,
        "relative_humidity_2m": 61,
        "wind_speed_10m": 14.2,
        "wind_direction_10m": 180,
        "wind_gusts_10m": 23.4,
        "weather_code": 1,
    }


@pytest.mark.asyncio
async def test_get_current_rejects_invalid_location_id():
    ctx = FakeContext()
    result = await weather.get_current(0, ctx=ctx)

    assert ctx.info_messages == []
    assert result == "Please provide a valid location id."


@pytest.mark.asyncio
async def test_get_current_reports_missing_location(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client([build_search_response([])])

    result = await weather.get_current(999, ctx=ctx)

    assert ctx.info_messages == ["resolving location for current conditions"]
    assert result == "Location not found."


@pytest.mark.asyncio
async def test_get_current_handles_upstream_errors(open_meteo_client):
    ctx = FakeContext()
    open_meteo_client([httpx.RequestError("network error")])

    result = await weather.get_current(12345, ctx=ctx)

    assert ctx.info_messages == ["resolving location for current conditions"]
    assert result == "Unable to fetch current conditions."
