# MCP Weather Server

Small MCP server backed by Open-Meteo.

## Tools

- `search_location(query)`
- `get_current(location_id)`
- `get_forecast(location_id, days=5)`

## Setup

```bash
uv sync
```

## Run

```bash
uv run python weather.py
```

## Tests

```bash
uv run pytest
```
