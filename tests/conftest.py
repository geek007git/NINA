"""Shared test fixtures and fakes.

The tools take an :class:`~nina.http_client.AsyncHttpClient`, so the whole
network layer is replaced by :class:`FakeHttp` here. No test in this suite
touches the network, which keeps them fast and deterministic in CI.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from nina.config import Settings


class FakeHttp:
    """An :class:`AsyncHttpClient` that replays canned responses.

    Routes are matched by substring against the request URL, so a test can set
    up geocoding and forecast responses independently.
    """

    def __init__(self, routes: dict[str, Any] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False
        #: Set to an exception instance to make every request raise it.
        self.raises: Exception | None = None

    def _resolve(self, method: str, url: str, payload: dict[str, Any]) -> Any:
        self.calls.append((method, url, payload))
        if self.raises is not None:
            raise self.raises
        for fragment, response in self.routes.items():
            if fragment in url:
                return response
        raise AssertionError(f"unexpected request to {url}")

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return self._resolve("GET", url, params or {})

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return self._resolve("POST", url, json or {})

    async def aclose(self) -> None:
        self.closed = True


def run(coro: Any) -> Any:
    """Run a coroutine to completion.

    Used instead of pytest-asyncio so the suite has exactly one test-time
    dependency.
    """
    return asyncio.run(coro)


@pytest.fixture
def base_env() -> dict[str, str]:
    """The minimum environment that produces a valid configuration."""
    return {
        "LIVEKIT_URL": "wss://example.livekit.cloud",
        "LIVEKIT_API_KEY": "devkey",
        "LIVEKIT_API_SECRET": "devsecret",
        "GOOGLE_API_KEY": "gkey",
    }


@pytest.fixture
def settings(base_env: dict[str, str], tmp_path: Any) -> Settings:
    """Valid settings with memory pointed at a temp directory."""
    from nina.config import load_settings

    env = dict(base_env)
    env["NINA_MEMORY_PATH"] = str(tmp_path / "memory.json")
    return load_settings(env)


GEOCODE_RESPONSE = {
    "results": [
        {
            "name": "Chennai",
            "admin1": "Tamil Nadu",
            "country": "India",
            "latitude": 13.08,
            "longitude": 80.27,
        }
    ]
}

FORECAST_RESPONSE = {
    "current": {
        "temperature_2m": 31.4,
        "apparent_temperature": 38.2,
        "relative_humidity_2m": 70,
        "weather_code": 2,
        "wind_speed_10m": 24.0,
    },
    "daily": {
        "temperature_2m_max": [33.1],
        "temperature_2m_min": [26.4],
        "precipitation_probability_max": [45],
    },
}
