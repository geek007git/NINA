"""A tiny async HTTP seam.

Tools depend on this protocol rather than on ``httpx`` directly. That keeps the
tool logic unit-testable without a network, a mock server, or monkeypatching a
third-party module, and it means swapping the transport later touches one file.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .errors import ToolError


@runtime_checkable
class AsyncHttpClient(Protocol):
    """Minimal async HTTP surface: the tools only ever need JSON."""

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...

    async def aclose(self) -> None: ...


class HttpxClient:
    """:class:`AsyncHttpClient` backed by ``httpx``.

    ``httpx`` is imported lazily so that importing :mod:`nina.tools` stays cheap
    and dependency-free for callers that inject their own client.
    """

    def __init__(self, *, timeout: float = 10.0, user_agent: str = "NINA/1.0") -> None:
        self._timeout = timeout
        self._user_agent = user_agent
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx  # noqa: PLC0415  (intentionally deferred)

            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            )
        return self._client

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return await self._request("GET", url, params=params, headers=headers)

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return await self._request("POST", url, json=json, headers=headers)

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        import httpx  # noqa: PLC0415

        client = self._ensure_client()
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise ToolError("that lookup timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(f"the service answered with status {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ToolError("I could not reach that service") from exc
        except ValueError as exc:  # malformed JSON body
            raise ToolError("the service returned something I could not read") from exc

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
