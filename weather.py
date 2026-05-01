import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

GEOCODING_API_BASE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API_BASE = "https://api.open-meteo.com/v1/forecast"


@mcp.tool()
async def get_forecast(city: str) -> str:
    if not city.strip():
        return "Please provide a city name."

    try:
        async with httpx.AsyncClient() as client:
            geocoding_response = await client.get(
                GEOCODING_API_BASE,
                params={"name": city, "count": 1},
                timeout=30.0,
            )
            geocoding_response.raise_for_status()
            geocoding_data = geocoding_response.json()

            results = geocoding_data.get("results", [])
            if not results:
                return "City not found."

            location = results[0]
            city_name = location["name"]
            forecast_response = await client.get(
                FORECAST_API_BASE,
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "forecast_days": 5,
                    "timezone": "auto",
                },
                timeout=30.0,
            )
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
    except Exception:
        return "Unable to fetch forecast data."

    daily = forecast_data.get("daily", {})
    times = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])

    if not times or not max_temps or not min_temps:
        return "Unable to fetch forecast data."

    lines = [f"5-day forecast for {city_name}:"]
    for date, max_temp, min_temp in zip(times[:5], max_temps[:5], min_temps[:5]):
        lines.append(f"{date}: High {max_temp}°C, Low {min_temp}°C")

    return "\n".join(lines)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
