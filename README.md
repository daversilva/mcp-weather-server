# MCP Weather Server

Small MCP server backed by Open-Meteo.

## Tools

- `search_location(query)` returns a `list[dict]` of canonical location matches (`id`, `name`, `latitude`, `longitude`, `timezone`, `country`, `admin1`, `feature_code`) for follow-up calls.
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
