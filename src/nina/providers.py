"""Builds the model stack for a session.

Two providers are supported and selected by ``NINA_PROVIDER``:

``google_realtime``
    One speech-to-speech model (Gemini Live). Lowest latency, most natural
    turn-taking, fewest moving parts. This is the default and matches what the
    project originally shipped.

``pipeline``
    Separate speech-to-text, LLM and text-to-speech stages routed through
    LiveKit's inference gateway. Slower, but each stage is swappable and you can
    read the transcript at every step.

Keeping the choice behind one function means adding a third provider later is a
local change, not a rewrite of the entrypoint.
"""

from __future__ import annotations

from typing import Any

from . import compat
from .config import PROVIDER_GOOGLE_REALTIME, PROVIDER_PIPELINE, Settings
from .errors import NinaError
from .logging_setup import get_logger

logger = get_logger("providers")


def build_session_kwargs(settings: Settings, instructions: str) -> dict[str, Any]:
    """Return the keyword arguments for ``AgentSession(...)``.

    Args:
        settings: Validated configuration.
        instructions: The system prompt. Realtime models want it at construction
            time; pipeline models take it from the agent instead.

    Raises:
        NinaError: if the configured provider is unknown or unavailable.
    """
    provider = settings.model.provider

    if provider == PROVIDER_GOOGLE_REALTIME:
        return {"llm": _build_google_realtime(settings, instructions)}

    if provider == PROVIDER_PIPELINE:
        return _build_pipeline(settings)

    raise NinaError(f"unknown provider {provider!r}")


def _build_google_realtime(settings: Settings, instructions: str) -> Any:
    realtime_cls = compat.load_realtime_model_cls()
    model = settings.model
    logger.info(
        "using Google realtime model",
        extra={"model": model.realtime_model, "voice": model.voice},
    )
    kwargs: dict[str, Any] = {
        "model": model.realtime_model,
        "voice": model.voice,
        "temperature": model.temperature,
        "instructions": instructions,
    }
    if settings.google_api_key:
        kwargs["api_key"] = settings.google_api_key
    return realtime_cls(**kwargs)


def _build_pipeline(settings: Settings) -> dict[str, Any]:
    inference = compat.load_inference()
    model = settings.model
    logger.info(
        "using STT/LLM/TTS pipeline",
        extra={"stt": model.stt_model, "llm": model.llm_model, "tts": model.tts_model},
    )

    tts_kwargs: dict[str, Any] = {}
    if model.tts_voice:
        tts_kwargs["voice"] = model.tts_voice

    return {
        "stt": inference.STT(model.stt_model, language=model.stt_language),
        "llm": inference.LLM(model.llm_model),
        "tts": inference.TTS(model.tts_model, **tts_kwargs),
    }


def describe(settings: Settings) -> str:
    """A one-line, human-readable summary of the configured stack."""
    model = settings.model
    if model.provider == PROVIDER_GOOGLE_REALTIME:
        return (
            f"google_realtime: {model.realtime_model} "
            f"(voice={model.voice}, temperature={model.temperature})"
        )
    return f"pipeline: stt={model.stt_model} llm={model.llm_model} tts={model.tts_model}"
