# MCP Weather Server

Small MCP server backed by Open-Meteo.

## Tools

- `search_location(query)` returns a `list[dict]` of canonical location matches (`id`, `name`, `latitude`, `longitude`, `timezone`, `country`, `admin1`, `feature_code`) for follow-up calls.
- `get_current(location_id)`
- `get_forecast(location_id, days=5)`

## Resources

- `config://units`
- `config://supported_regions`

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
