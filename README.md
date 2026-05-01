# MCP Weather Server

Small MCP server that exposes a single weather tool backed by Open-Meteo.

## What It Does

- Entry point: `weather.py`
- Transport: `stdio`
- Tool: `get_forecast(city)`
- Behavior: geocodes the city, then returns a 5-day forecast with daily high/low temperatures

## Setup

```bash
uv sync
```

## Run

```bash
uv run python weather.py
```

## Dependencies

- `httpx` for Open-Meteo requests
- `mcp[cli]` for the FastMCP server
- `pytest` and `pytest-asyncio` for tests

## Tests

```bash
uv run pytest
```

The suite covers:

- normal forecast formatting
- city names with spaces
- empty city input
- unknown cities
- geocoding and forecast request failures
