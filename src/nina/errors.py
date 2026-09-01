"""Exception types raised by NINA.

A single base class means callers (and the CLI) can distinguish "the operator
made a mistake" from "something genuinely broke", and present the former
without a traceback.
"""

from __future__ import annotations

from collections.abc import Iterable


class NinaError(Exception):
    """Base class for every error raised deliberately by NINA."""


class ConfigError(NinaError):
    """Raised when the environment configuration is missing or invalid.

    Carries *all* problems found rather than only the first, so an operator can
    fix their ``.env`` in one pass instead of playing whack-a-mole.
    """

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems: list[str] = list(problems)
        detail = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"Invalid NINA configuration:\n{detail}")


class ToolError(NinaError):
    """Raised inside a tool when it cannot produce a useful answer.

    Tools convert this into a short spoken sentence rather than letting it
    bubble up and kill the session.
    """


class MemoryError_(NinaError):
    """Raised when the persistent memory store cannot be read or written."""
