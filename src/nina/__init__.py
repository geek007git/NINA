"""NINA - a realtime voice AI assistant built on LiveKit Agents.

The package is deliberately layered so that everything except :mod:`nina.providers`
and :mod:`nina.runtime` is importable without the heavy LiveKit/AI dependencies
installed.  That keeps configuration, persona rendering, memory and the tool
implementations unit-testable in isolation.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
