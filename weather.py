import httpx

from mcp_weather_server.weather import (
    SUPPORTED_REGIONS,
    get_current,
    get_forecast,
    main,
    mcp,
    search_location,
    trip_weather_briefing,
)


if __name__ == "__main__":
    main()
