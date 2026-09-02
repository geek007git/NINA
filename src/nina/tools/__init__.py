"""Tool implementations, kept free of any LiveKit dependency.

Each function here is plain async Python that returns a short, speakable string
or raises :class:`nina.errors.ToolError`. :mod:`nina.agent` is the only place
that knows about ``@function_tool``, which means every tool can be exercised in
tests without installing the agent framework.
"""

from __future__ import annotations

from .clock import current_time, resolve_zone
from .weather import get_weather
from .websearch import search

__all__ = ["current_time", "get_weather", "resolve_zone", "search"]
