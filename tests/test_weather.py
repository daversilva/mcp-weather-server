import httpx
import pytest

import weather
from conftest import MockResponse


def build_geocoding_response(name: str, latitude: float, longitude: float) -> MockResponse:
    return MockResponse(
        {
            "results": [
                {"name": name, "latitude": latitude, "longitude": longitude},
            ]
        }
    )


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
            }
        }
    )


@pytest.mark.asyncio
async def test_get_forecast_formats_city_and_daily_lines(open_meteo_client):
    open_meteo_client(
        [
            build_geocoding_response("Goiania", -16.6869, -49.2648),
            build_forecast_response(
                [
                    "2026-05-01",
                    "2026-05-02",
                    "2026-05-03",
                    "2026-05-04",
                    "2026-05-05",
                ],
                [30.0, 29.0, 28.0, 27.0, 26.0],
                [20.0, 19.0, 18.0, 17.0, 16.0],
            ),
        ]
    )

    result = await weather.get_forecast("Goiania")

    assert "Goiania" in result
    assert "2026-05-01" in result
    assert "2026-05-05" in result


@pytest.mark.asyncio
async def test_get_forecast_supports_city_with_spaces(open_meteo_client):
    open_meteo_client(
        [
            build_geocoding_response("New York", 40.7128, -74.0060),
            build_forecast_response(
                [
                    "2026-05-01",
                    "2026-05-02",
                    "2026-05-03",
                    "2026-05-04",
                    "2026-05-05",
                ],
                [24.0, 23.0, 22.0, 21.0, 20.0],
                [15.0, 14.0, 13.0, 12.0, 11.0],
            ),
        ]
    )

    result = await weather.get_forecast("New York")

    assert "New York" in result


@pytest.mark.asyncio
async def test_get_forecast_rejects_empty_city():
    result = await weather.get_forecast("")
    assert result == "Please provide a city name."


@pytest.mark.asyncio
async def test_get_forecast_city_not_found(open_meteo_client):
    open_meteo_client([MockResponse({"results": []})])

    result = await weather.get_forecast("Unknown City")

    assert result == "City not found."


@pytest.mark.asyncio
async def test_get_forecast_geocoding_error_returns_fetch_error(open_meteo_client):
    open_meteo_client([httpx.RequestError("network error")])

    result = await weather.get_forecast("Goiania")

    assert result == "Unable to fetch forecast data."


@pytest.mark.asyncio
async def test_get_forecast_forecast_api_error_returns_fetch_error(open_meteo_client):
    open_meteo_client(
        [
            build_geocoding_response("Goiania", -16.6869, -49.2648),
            httpx.RequestError("network error"),
        ]
    )

    result = await weather.get_forecast("Goiania")

    assert result == "Unable to fetch forecast data."
