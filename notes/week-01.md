# Week 01 — MCP Weather Server (CCAF Study Notes)

> Goal: connect MCP theory to the current codebase and document the hardened runtime behavior that now ships in this repository.

## MCP fundamentals in this project

This server exposes all three MCP primitives through FastMCP:

- Tool: `search_location`, `get_forecast`, `get_current`
- Resource: `config://units`, `config://supported_regions`
- Prompt: `trip_weather_briefing(destination, days)`

The transport remains `stdio`, so host applications run this as a local process and exchange JSON-RPC messages over stdin/stdout.

## Current entrypoint architecture

The project has two explicit startup paths and they are intentionally aligned:

- Module entrypoint: `python -m mcp_weather_server`
- Script entrypoint: `mcp-weather-server` (from `[project.scripts]`)

Implementation details:

- `mcp_weather_server/__main__.py` imports and runs `main()`.
- `mcp_weather_server/weather.py` defines `main()` and calls `mcp.run(transport="stdio")`.
- Top-level `weather.py` is a compatibility shim that re-exports the package symbols used by tests and legacy imports.

This means module execution is first-class, while the top-level file remains for backwards compatibility.

## Hardening now in place

### Lifespan-managed shared HTTP client

`FastMCP(..., lifespan=_lifespan)` initializes one `httpx.AsyncClient(timeout=30.0)` per app lifespan. The client is stored in lifespan context and reused by tool calls when context is available.

Fallback behavior is still safe: if no lifespan context exists, `_http_client` creates a temporary client for that call.

### Structured logging and operational signals

Runtime events are emitted as JSON text on stderr via `_log_event`, including:

- `lifespan.start` / `lifespan.stop`
- `search_location.request` and error events
- `get_forecast.request` / `get_forecast.location_missing` / error events
- `get_current.request` / `get_current.location_missing` / error events

Tool handlers also send user-facing progress notifications through `ctx.info(...)` when context is provided.

### Resource loading hardening

`config://supported_regions` is loaded from bundled package data using `importlib.resources`, not relative file paths. This keeps behavior stable across install/run environments.

## Tool contract and data flow

### `search_location(query)`

- Purpose: resolve ambiguous place names.
- Returns canonical matches with `id`, `name`, coordinates, timezone, and region fields.
- Should be called before `get_forecast` and `get_current`.

### `get_forecast(location_id, days=5)`

- Validates `location_id > 0` and `1 <= days <= 7`.
- Resolves `location_id` to coordinates via geocoding, then fetches daily forecast.
- Returns `{location, days, units}`.

### `get_current(location_id)`

- Validates `location_id > 0`.
- Resolves `location_id`, then fetches current conditions.
- Returns `{location, current, units}`.

Both weather tools share the same two-hop pattern: id resolution first, weather fetch second.

## Current tests and coverage shape

The suite currently passes as:

- `24 passed` (`uv run pytest`)

Coverage is behavior-oriented and includes:

- MCP registration metadata for tools/resources/prompts.
- Prompt rendering checks for `trip_weather_briefing`.
- Resource read checks for units and supported regions.
- Success/error/validation paths for `search_location`, `get_forecast`, `get_current`.
- Lifespan shared-client reuse verification.
- Bootstrap test that `main()` starts FastMCP with `transport="stdio"`.

## Quick runtime checks

```bash
uv run pytest
uv run python -m mcp_weather_server
```

The second command starts the MCP stdio server and runs until the host process stops it.
