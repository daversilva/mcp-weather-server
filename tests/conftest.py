import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import weather


class MockResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "https://example.com"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._payload


class MockAsyncClient:
    def __init__(self, responses: list[MockResponse | Exception]):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, timeout: float = 30.0, params: dict | None = None):
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


@pytest.fixture
def open_meteo_client(monkeypatch: pytest.MonkeyPatch):
    def _patch(responses: list[MockResponse | Exception]) -> None:
        monkeypatch.setattr(weather.httpx, "AsyncClient", lambda: MockAsyncClient(responses))

    return _patch
