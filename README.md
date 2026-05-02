# MCP Weather Server

Small MCP server backed by Open-Meteo.

## Tools

- `search_location(query)` returns a `list[dict]` of canonical location matches (`id`, `name`, `latitude`, `longitude`, `timezone`, `country`, `admin1`, `feature_code`) for follow-up calls.
- `get_current(location_id)`
- `get_forecast(location_id, days=5)`

## Prompts

- `trip_weather_briefing(destination, days)` plans a trip weather check by calling `search_location`, then `get_forecast`, then summarizing what to pack.

## Resources

- `config://units`
- `config://supported_regions`

## Setup

```bash
uv sync
```

## Run

```bash
uv run python -m mcp_weather_server
```

Or, if installed as a script:

```bash
mcp-weather-server
```

## Tests

```bash
uv run pytest
```
