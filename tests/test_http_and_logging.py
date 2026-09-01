"""HTTP error mapping and logging setup."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from conftest import run
from nina.errors import ToolError
from nina.http_client import HttpxClient
from nina.logging_setup import JsonFormatter, configure_logging, get_logger


class _RaisingClient:
    """Stands in for ``httpx.AsyncClient`` and raises on every request."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.closed = False

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        raise self._exc

    async def aclose(self) -> None:
        self.closed = True


def _client_raising(exc: Exception) -> HttpxClient:
    client = HttpxClient()
    client._client = _RaisingClient(exc)  # noqa: SLF001 - injecting the transport
    return client


def test_timeouts_become_a_speakable_tool_error() -> None:
    client = _client_raising(httpx.TimeoutException("timed out"))
    with pytest.raises(ToolError, match="timed out"):
        run(client.get_json("https://example.com"))


def test_http_status_errors_report_the_code() -> None:
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(503, request=request)
    client = _client_raising(httpx.HTTPStatusError("bad", request=request, response=response))
    with pytest.raises(ToolError, match="status 503"):
        run(client.get_json("https://example.com"))


def test_connection_errors_are_wrapped() -> None:
    client = _client_raising(httpx.ConnectError("no route"))
    with pytest.raises(ToolError, match="could not reach"):
        run(client.get_json("https://example.com"))


def test_malformed_json_is_wrapped() -> None:
    client = _client_raising(ValueError("not json"))
    with pytest.raises(ToolError, match="could not read"):
        run(client.get_json("https://example.com"))


def test_aclose_is_safe_when_never_used() -> None:
    run(HttpxClient().aclose())


def test_aclose_closes_an_open_client() -> None:
    client = HttpxClient()
    fake = _RaisingClient(httpx.ConnectError("x"))
    client._client = fake  # noqa: SLF001
    run(client.aclose())
    assert fake.closed is True
    assert client._client is None  # noqa: SLF001


# --- logging --------------------------------------------------------------


def test_configure_logging_is_idempotent() -> None:
    """The LiveKit CLI can re-enter process setup; handlers must not stack up."""
    first = configure_logging("INFO", "text")
    count = len(first.handlers)
    second = configure_logging("INFO", "text")
    assert len(second.handlers) == count == 1


def test_json_formatter_emits_parseable_lines() -> None:
    record = logging.LogRecord(
        name="nina.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "nina.test"


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.LogRecord(
        name="nina.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="event",
        args=(),
        exc_info=None,
    )
    record.room = "room-42"  # type: ignore[attr-defined]
    payload = json.loads(JsonFormatter().format(record))
    assert payload["room"] == "room-42"


def test_get_logger_returns_children_of_the_root_nina_logger() -> None:
    assert get_logger().name == "nina"
    assert get_logger("agent").name == "nina.agent"
