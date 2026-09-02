"""The NINA agent and its tools.

This is the only module that knows about ``@function_tool``. Every tool here is
a thin, guarded wrapper around the plain async functions in :mod:`nina.tools`,
which keeps the interesting logic testable without the agent framework
installed.

Tools are registered dynamically from configuration rather than declared as
decorated methods, so disabling a tool actually removes it from the model's
toolset instead of leaving it advertised and failing at call time.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from . import compat
from .config import Settings
from .errors import NinaError, ToolError
from .http_client import AsyncHttpClient, HttpxClient
from .logging_setup import get_logger
from .memory import MemoryStore, NullMemoryStore
from .persona import build_instructions
from .tools import clock, weather, websearch

logger = get_logger("agent")

#: The tool signatures below annotate their first parameter as ``RunContext``,
#: which LiveKit resolves with ``typing.get_type_hints`` at registration time.
#: Because this module uses ``from __future__ import annotations``, those
#: annotations are strings resolved against *this module's* globals - so the name
#: has to live here, not as a local inside :func:`build_tools`, or resolution
#: fails with ``NameError``. It starts as ``Any`` so importing this module never
#: requires LiveKit, and :func:`build_tools` rebinds it to the real class.
RunContext: Any = Any


@dataclass(slots=True)
class ToolDeps:
    """Everything the tools need, injected rather than reached for."""

    settings: Settings
    http: AsyncHttpClient
    memory: MemoryStore

    @classmethod
    def from_settings(cls, settings: Settings) -> ToolDeps:
        """Build the default dependency set from configuration."""
        if settings.memory.enabled:
            memory: MemoryStore = MemoryStore(
                settings.memory.path,
                max_items=settings.memory.max_items,
                max_value_chars=settings.memory.max_value_chars,
            )
            memory.load()
        else:
            memory = NullMemoryStore()
        return cls(
            settings=settings,
            http=HttpxClient(timeout=settings.http_timeout),
            memory=memory,
        )

    async def aclose(self) -> None:
        await self.http.aclose()


def guard(name: str) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
    """Wrap a tool so it never raises into the session.

    An exception escaping a tool call ends the conversation. A sentence the
    model can read out ("I could not reach that service") keeps it alive and
    lets the model recover, so failures are converted rather than propagated.
    """

    def decorator(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            try:
                result = await fn(*args, **kwargs)
            except ToolError as exc:
                logger.info("tool declined", extra={"tool": name, "reason": str(exc)})
                return str(exc)
            except NinaError as exc:
                logger.warning("tool failed", extra={"tool": name, "error": str(exc)})
                return f"I hit a problem with that: {exc}"
            except Exception:
                logger.exception("tool crashed", extra={"tool": name})
                return "Something went wrong on my side with that one."
            logger.debug("tool ok", extra={"tool": name})
            return result

        return wrapper

    return decorator


def build_tools(deps: ToolDeps) -> list[Any]:
    """Create the LiveKit tool objects for the enabled tool set.

    Args:
        deps: Injected settings, HTTP client and memory store.

    Returns:
        A list of ``function_tool`` objects ready to hand to ``Agent``.
    """
    global RunContext  # noqa: PLW0603 - see the note on RunContext above

    function_tool = compat.load_function_tool()
    RunContext = compat.load_run_context()
    settings = deps.settings
    tools: list[Any] = []

    if settings.tool_enabled("clock"):

        @guard("clock")
        async def get_current_time(context: RunContext, timezone: str = "UTC") -> str:  # type: ignore[valid-type]
            """Get the current date and time in a given timezone.

            Call this whenever the user asks what time or what day it is, or asks
            about the time somewhere else in the world. Never guess the time.

            Args:
                timezone: An IANA timezone like "Asia/Kolkata", an abbreviation
                    like "IST", or a city name like "London". Defaults to UTC.
            """
            return clock.current_time(timezone)

        tools.append(function_tool(get_current_time))

    if settings.tool_enabled("weather"):

        @guard("weather")
        async def get_weather(context: RunContext, location: str) -> str:  # type: ignore[valid-type]
            """Get current weather conditions and today's forecast for a place.

            Call this whenever the user asks about weather, temperature, or
            whether they should take a jacket. Never guess the weather.

            Args:
                location: A city or region name, for example "Chennai" or
                    "San Francisco".
            """
            return await weather.get_weather(location, deps.http)

        tools.append(function_tool(get_weather))

    if settings.tool_enabled("search") and settings.search_provider != "none":

        @guard("search")
        async def search_web(context: RunContext, query: str) -> str:  # type: ignore[valid-type]
            """Search the web for recent or factual information.

            Call this when the user asks about current events, specific facts,
            or anything you are not confident about. Prefer looking it up over
            guessing.

            Args:
                query: A short search query, phrased as you would type it.
            """
            return await websearch.search(
                query,
                deps.http,
                provider=settings.search_provider,
                api_key=settings.tavily_api_key,
            )

        tools.append(function_tool(search_web))

    if settings.tool_enabled("memory") and settings.memory.enabled:

        @guard("remember")
        async def remember(context: RunContext, key: str, value: str) -> str:  # type: ignore[valid-type]
            """Save a fact so it is available in future conversations.

            Call this when the user tells you something worth keeping, such as a
            preference, a schedule, or a goal. Confirm briefly afterwards.

            Args:
                key: A short label for the fact, for example "gym schedule".
                value: The fact itself, in one sentence.
            """
            try:
                item = deps.memory.remember(key, value)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
            return f"Saved that under {item.key}."

        @guard("recall")
        async def recall(context: RunContext, key: str) -> str:  # type: ignore[valid-type]
            """Look up a fact saved in an earlier conversation.

            Call this before saying you do not know something personal about the
            user, in case you already recorded it.

            Args:
                key: The label of the fact to look up, for example
                    "gym schedule".
            """
            item = deps.memory.recall(key)
            if item is None:
                return f"I have nothing saved about {key}."
            return f"{item.key}: {item.value}"

        @guard("forget")
        async def forget(context: RunContext, key: str) -> str:  # type: ignore[valid-type]
            """Delete a previously saved fact.

            Args:
                key: The label of the fact to remove.
            """
            removed = deps.memory.forget(key)
            return f"Removed {key}." if removed else f"I had nothing saved about {key}."

        @guard("list_memories")
        async def list_memories(context: RunContext) -> str:  # type: ignore[valid-type]
            """List the labels of everything currently saved in memory.

            Use this when the user asks what you remember about them.
            """
            items = deps.memory.all_items()
            if not items:
                return "I have not saved anything yet."
            # Cap the spoken list; reading out two hundred labels helps nobody.
            labels = [item.key for item in items[:12]]
            more = len(items) - len(labels)
            spoken = ", ".join(labels)
            return spoken + (f", and {more} more." if more > 0 else ".")

        tools.extend(function_tool(fn) for fn in (remember, recall, forget, list_memories))

    logger.info("tools registered", extra={"count": len(tools)})
    return tools


def build_agent(deps: ToolDeps) -> Any:
    """Construct the :class:`Agent` subclass instance for a session."""
    agents = compat.load_agents()
    settings = deps.settings
    instructions = build_instructions(settings.persona, tools=settings.tools)

    class NinaAgent(agents.Agent):  # type: ignore[misc, name-defined]
        """NINA, as the agent framework sees her."""

        def __init__(self) -> None:
            super().__init__(instructions=instructions, tools=build_tools(deps))

    return NinaAgent()
