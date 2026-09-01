"""Environment-driven configuration.

Everything NINA needs is read once, validated once, and then passed around as an
immutable :class:`Settings` object. Reading ``os.environ`` from deep inside the
call stack is how configuration bugs turn into runtime surprises in a process
that only fails when someone is talking to it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

from .errors import ConfigError

Env = Mapping[str, str]

#: Providers understood by :mod:`nina.providers`.
PROVIDER_GOOGLE_REALTIME: Final = "google_realtime"
PROVIDER_PIPELINE: Final = "pipeline"
PROVIDERS: Final = (PROVIDER_GOOGLE_REALTIME, PROVIDER_PIPELINE)

#: Tools that can be toggled via ``NINA_TOOLS``.
ALL_TOOLS: Final = ("clock", "weather", "search", "memory")

NOISE_CANCELLATION_MODES: Final = ("bvc", "bvc_telephony", "none")
SEARCH_PROVIDERS: Final = ("duckduckgo", "tavily", "none")
LOG_FORMATS: Final = ("text", "json")
LOG_LEVELS: Final = ("debug", "info", "warning", "error", "critical")

_TRUE = frozenset({"1", "true", "yes", "on", "y"})
_FALSE = frozenset({"0", "false", "no", "off", "n"})

#: Substrings that mark a config field as secret for redaction purposes.
_SECRET_MARKERS = ("api_secret", "api_key", "secret", "token", "password")


class _Reader:
    """Reads and validates env values, accumulating problems instead of raising.

    Reporting every problem at once means an operator fixes their ``.env`` in a
    single pass rather than one failed start per typo.
    """

    def __init__(self, env: Env) -> None:
        self._env = env
        self.problems: list[str] = []

    def str_(self, key: str, default: str = "", *, required: bool = False) -> str:
        raw = self._env.get(key, "").strip()
        if not raw:
            if required:
                self.problems.append(f"{key} is required but not set")
            return default
        return raw

    def bool_(self, key: str, default: bool) -> bool:
        raw = self._env.get(key, "").strip().lower()
        if not raw:
            return default
        if raw in _TRUE:
            return True
        if raw in _FALSE:
            return False
        self.problems.append(f"{key}={raw!r} is not a boolean (use true or false)")
        return default

    def float_(self, key: str, default: float, *, lo: float, hi: float) -> float:
        raw = self._env.get(key, "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            self.problems.append(f"{key}={raw!r} is not a number")
            return default
        if not lo <= value <= hi:
            self.problems.append(f"{key}={value} is outside the allowed range [{lo}, {hi}]")
            return default
        return value

    def int_(self, key: str, default: int, *, lo: int, hi: int) -> int:
        raw = self._env.get(key, "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            self.problems.append(f"{key}={raw!r} is not an integer")
            return default
        if not lo <= value <= hi:
            self.problems.append(f"{key}={value} is outside the allowed range [{lo}, {hi}]")
            return default
        return value

    def choice(self, key: str, default: str, allowed: tuple[str, ...]) -> str:
        raw = self._env.get(key, "").strip().lower()
        if not raw:
            return default
        if raw not in allowed:
            self.problems.append(f"{key}={raw!r} must be one of: {', '.join(allowed)}")
            return default
        return raw

    def csv(self, key: str, default: tuple[str, ...], allowed: tuple[str, ...]) -> tuple[str, ...]:
        raw = self._env.get(key, "").strip()
        if not raw:
            return default
        if raw.lower() == "none":
            return ()
        # dict.fromkeys de-duplicates while preserving the operator's ordering.
        items = tuple(dict.fromkeys(p.strip().lower() for p in raw.split(",") if p.strip()))
        unknown = [i for i in items if i not in allowed]
        if unknown:
            self.problems.append(
                f"{key} contains unknown entries: {', '.join(unknown)} "
                f"(allowed: {', '.join(allowed)})"
            )
            return tuple(i for i in items if i in allowed)
        return items


#: Declared as a module constant rather than read back off the dataclass:
#: with ``slots=True`` the class attribute is a slot descriptor, not the default.
DEFAULT_INTERESTS: Final = (
    "basketball",
    "badminton",
    "creative writing",
    "audio and audiophile gear",
    "software, hardware, and prompt engineering",
)


@dataclass(frozen=True, slots=True)
class PersonaSettings:
    """Who NINA is, and who she is talking to."""

    assistant_name: str = "NINA"
    user_name: str = "Shan"
    user_full_name: str = "Shanmuga Priyan"
    interests: tuple[str, ...] = DEFAULT_INTERESTS
    extra_instructions: str = ""
    greet_on_start: bool = True


@dataclass(frozen=True, slots=True)
class ModelSettings:
    """Which speech and reasoning stack sits behind the session."""

    provider: str = PROVIDER_GOOGLE_REALTIME
    # Realtime (single speech-to-speech model) path.
    realtime_model: str = "gemini-2.0-flash-exp"
    voice: str = "Puck"
    temperature: float = 0.8
    # STT -> LLM -> TTS path, expressed as LiveKit inference model ids.
    stt_model: str = "deepgram/nova-3"
    stt_language: str = "multi"
    llm_model: str = "google/gemini-2.0-flash"
    tts_model: str = "cartesia/sonic-2"
    tts_voice: str = ""


@dataclass(frozen=True, slots=True)
class MemorySettings:
    """Persistent, cross-session recall."""

    enabled: bool = True
    path: Path = field(default_factory=lambda: Path(".nina/memory.json"))
    max_items: int = 200
    max_value_chars: int = 500


@dataclass(frozen=True, slots=True)
class Settings:
    """Fully validated configuration for one NINA process."""

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    google_api_key: str = ""
    tavily_api_key: str = ""

    persona: PersonaSettings = field(default_factory=PersonaSettings)
    model: ModelSettings = field(default_factory=ModelSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)

    tools: tuple[str, ...] = ALL_TOOLS
    search_provider: str = "duckduckgo"
    noise_cancellation: str = "bvc"
    http_timeout: float = 10.0

    log_level: str = "INFO"
    log_format: str = "text"

    def tool_enabled(self, name: str) -> bool:
        return name in self.tools

    def with_overrides(self, **kwargs: Any) -> Settings:
        """Return a copy with top-level fields replaced."""
        return replace(self, **kwargs)

    def redacted(self) -> dict[str, Any]:
        """A flat dict safe to log: secrets become ``***`` or ``<unset>``."""
        out: dict[str, Any] = {}
        for key, value in _flatten(self).items():
            if any(marker in key for marker in _SECRET_MARKERS):
                out[key] = "***" if value else "<unset>"
            else:
                out[key] = value
        return out


_TOP_LEVEL_FIELDS: Final = (
    "livekit_url",
    "livekit_api_key",
    "livekit_api_secret",
    "google_api_key",
    "tavily_api_key",
    "tools",
    "search_provider",
    "noise_cancellation",
    "http_timeout",
    "log_level",
    "log_format",
)


def _flatten(settings: Settings) -> dict[str, Any]:
    """Flatten nested settings into ``group.field`` keys for logging."""
    flat: dict[str, Any] = {name: getattr(settings, name) for name in _TOP_LEVEL_FIELDS}
    for group_name in ("persona", "model", "memory"):
        group = getattr(settings, group_name)
        for slot in group.__slots__:
            value = getattr(group, slot)
            flat[f"{group_name}.{slot}"] = str(value) if isinstance(value, Path) else value
    return flat


def load_settings(env: Env | None = None, *, require_credentials: bool = True) -> Settings:
    """Build :class:`Settings` from ``env``, defaulting to ``os.environ``.

    Args:
        env: Mapping to read from. Injectable so tests never touch the process
            environment.
        require_credentials: When ``False``, LiveKit and provider credentials are
            optional. Used by config inspection paths that should describe a
            setup without demanding it be complete.

    Returns:
        A validated, immutable :class:`Settings`.

    Raises:
        ConfigError: if any value is missing or malformed. Every problem found is
            reported together.
    """
    env = os.environ if env is None else env
    r = _Reader(env)

    livekit_url = r.str_("LIVEKIT_URL", required=require_credentials)
    if livekit_url:
        if "<" in livekit_url or ">" in livekit_url:
            r.problems.append("LIVEKIT_URL still contains the .env.example placeholder")
        elif not livekit_url.startswith(("ws://", "wss://")):
            r.problems.append(f"LIVEKIT_URL={livekit_url!r} must start with ws:// or wss://")

    provider = r.choice("NINA_PROVIDER", PROVIDER_GOOGLE_REALTIME, PROVIDERS)

    google_api_key = r.str_("GOOGLE_API_KEY")
    if provider == PROVIDER_GOOGLE_REALTIME and require_credentials and not google_api_key:
        r.problems.append("GOOGLE_API_KEY is required when NINA_PROVIDER=google_realtime")

    tools = r.csv("NINA_TOOLS", ALL_TOOLS, ALL_TOOLS)
    search_provider = r.choice("NINA_SEARCH_PROVIDER", "duckduckgo", SEARCH_PROVIDERS)
    tavily_api_key = r.str_("TAVILY_API_KEY")
    if "search" in tools and search_provider == "tavily" and not tavily_api_key:
        r.problems.append("TAVILY_API_KEY is required when NINA_SEARCH_PROVIDER=tavily")

    interests_raw = r.str_("NINA_INTERESTS")
    persona = PersonaSettings(
        assistant_name=r.str_("NINA_ASSISTANT_NAME", "NINA"),
        user_name=r.str_("NINA_USER_NAME", "Shan"),
        user_full_name=r.str_("NINA_USER_FULL_NAME", "Shanmuga Priyan"),
        interests=(
            tuple(p.strip() for p in interests_raw.split(",") if p.strip())
            if interests_raw
            else DEFAULT_INTERESTS
        ),
        extra_instructions=r.str_("NINA_EXTRA_INSTRUCTIONS"),
        greet_on_start=r.bool_("NINA_GREET_ON_START", True),
    )

    model = ModelSettings(
        provider=provider,
        realtime_model=r.str_("NINA_REALTIME_MODEL", "gemini-2.0-flash-exp"),
        voice=r.str_("NINA_VOICE", "Puck"),
        temperature=r.float_("NINA_TEMPERATURE", 0.8, lo=0.0, hi=2.0),
        stt_model=r.str_("NINA_STT_MODEL", "deepgram/nova-3"),
        stt_language=r.str_("NINA_STT_LANGUAGE", "multi"),
        llm_model=r.str_("NINA_LLM_MODEL", "google/gemini-2.0-flash"),
        tts_model=r.str_("NINA_TTS_MODEL", "cartesia/sonic-2"),
        tts_voice=r.str_("NINA_TTS_VOICE"),
    )

    memory = MemorySettings(
        enabled=r.bool_("NINA_MEMORY_ENABLED", True) and "memory" in tools,
        path=Path(r.str_("NINA_MEMORY_PATH", ".nina/memory.json")).expanduser(),
        max_items=r.int_("NINA_MEMORY_MAX_ITEMS", 200, lo=1, hi=10_000),
        max_value_chars=r.int_("NINA_MEMORY_MAX_VALUE_CHARS", 500, lo=16, hi=10_000),
    )

    settings = Settings(
        livekit_url=livekit_url,
        livekit_api_key=r.str_("LIVEKIT_API_KEY", required=require_credentials),
        livekit_api_secret=r.str_("LIVEKIT_API_SECRET", required=require_credentials),
        google_api_key=google_api_key,
        tavily_api_key=tavily_api_key,
        persona=persona,
        model=model,
        memory=memory,
        tools=tools,
        search_provider=search_provider,
        noise_cancellation=r.choice("NINA_NOISE_CANCELLATION", "bvc", NOISE_CANCELLATION_MODES),
        http_timeout=r.float_("NINA_HTTP_TIMEOUT", 10.0, lo=1.0, hi=120.0),
        log_level=r.choice("NINA_LOG_LEVEL", "info", LOG_LEVELS).upper(),
        log_format=r.choice("NINA_LOG_FORMAT", "text", LOG_FORMATS),
    )

    if r.problems:
        raise ConfigError(r.problems)
    return settings
