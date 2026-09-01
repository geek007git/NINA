"""Version-tolerant access to the LiveKit Agents API.

The LiveKit Agents 1.x line has moved names around between releases: the Google
plugin exposes the realtime model at both ``google.realtime`` and
``google.beta.realtime``, ``function_tool`` lives in both ``livekit.agents`` and
``livekit.agents.llm``, and the worker entrypoint has grown an ``AgentServer``
form alongside the original ``WorkerOptions``. Rather than pinning to one exact
release, every one of those lookups is resolved here at import time.

Nothing else in the package imports LiveKit directly, so if the upstream API
moves again this is the only file that needs to change.
"""

from __future__ import annotations

from typing import Any

from .errors import NinaError


class LiveKitUnavailableError(NinaError):
    """Raised when the LiveKit Agents packages are not importable."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"{detail}\n"
            "Install the runtime dependencies first:\n"
            "    pip install -e .\n"
            "or:\n"
            "    pip install -r requirements.txt"
        )


def _first_attr(obj: Any, *names: str) -> Any | None:
    """Return the first attribute in ``names`` that exists on ``obj``."""
    for name in names:
        found = obj
        try:
            for part in name.split("."):
                found = getattr(found, part)
        except AttributeError:
            continue
        return found
    return None


def load_agents() -> Any:
    """Import and return the ``livekit.agents`` module."""
    try:
        from livekit import agents  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise LiveKitUnavailableError(f"could not import livekit.agents ({exc})") from exc
    return agents


def load_function_tool() -> Any:
    """Return the ``function_tool`` decorator, wherever it currently lives."""
    agents = load_agents()
    tool = _first_attr(agents, "function_tool", "llm.function_tool")
    if tool is None:  # pragma: no cover - defensive
        raise LiveKitUnavailableError(
            "livekit.agents does not expose function_tool; the installed version "
            "is older than this project supports (needs livekit-agents >= 1.0)"
        )
    return tool


def load_run_context() -> Any:
    """Return the ``RunContext`` type, or ``object`` if this build lacks it.

    Falling back to ``object`` keeps the tool annotations valid; LiveKit only
    uses the annotation to decide which parameter is the context.
    """
    agents = load_agents()
    return _first_attr(agents, "RunContext", "llm.RunContext") or object


def load_realtime_model_cls() -> Any:
    """Return the Google realtime model class.

    Tries the stable ``google.realtime`` path first and falls back to the
    ``google.beta.realtime`` path used by earlier 1.x releases.
    """
    try:
        from livekit.plugins import google  # noqa: PLC0415
    except ImportError as exc:
        raise LiveKitUnavailableError(
            f"could not import the Google plugin ({exc}); "
            "install it with: pip install 'livekit-agents[google]~=1.0'"
        ) from exc

    cls = _first_attr(google, "realtime.RealtimeModel", "beta.realtime.RealtimeModel")
    if cls is None:  # pragma: no cover - defensive
        raise LiveKitUnavailableError(
            "the installed livekit-plugins-google does not expose a RealtimeModel"
        )
    return cls


def load_noise_cancellation(mode: str) -> Any | None:
    """Return a noise-cancellation filter instance, or ``None``.

    Noise cancellation is a LiveKit Cloud enhancement. Self-hosted deployments
    do not have it, and the plugin may be absent, so a missing filter degrades
    to "no filter" with a warning rather than failing the session.
    """
    if mode == "none":
        return None
    try:
        from livekit.plugins import noise_cancellation  # noqa: PLC0415
    except ImportError:
        return None

    attr = "BVCTelephony" if mode == "bvc_telephony" else "BVC"
    factory = getattr(noise_cancellation, attr, None)
    return factory() if factory is not None else None


def load_inference() -> Any:
    """Return ``livekit.agents.inference`` for the STT/LLM/TTS pipeline path."""
    agents = load_agents()
    inference = getattr(agents, "inference", None)
    if inference is None:
        raise LiveKitUnavailableError(
            "this livekit-agents build has no `inference` module, so the "
            "STT/LLM/TTS pipeline provider is unavailable. Either upgrade "
            "livekit-agents or set NINA_PROVIDER=google_realtime"
        )
    return inference
