"""Configuration loading and validation."""

from __future__ import annotations

import pytest

from nina.config import (
    ALL_TOOLS,
    PROVIDER_GOOGLE_REALTIME,
    PROVIDER_PIPELINE,
    load_settings,
)
from nina.errors import ConfigError


def test_valid_env_produces_defaults(base_env: dict[str, str]) -> None:
    settings = load_settings(base_env)

    assert settings.livekit_url == "wss://example.livekit.cloud"
    assert settings.model.provider == PROVIDER_GOOGLE_REALTIME
    assert settings.tools == ALL_TOOLS
    assert settings.persona.user_name == "Shan"
    assert settings.log_level == "INFO"


def test_missing_credentials_are_reported_together() -> None:
    with pytest.raises(ConfigError) as exc_info:
        load_settings({})

    problems = exc_info.value.problems
    assert any("LIVEKIT_URL" in p for p in problems)
    assert any("LIVEKIT_API_KEY" in p for p in problems)
    assert any("LIVEKIT_API_SECRET" in p for p in problems)
    assert any("GOOGLE_API_KEY" in p for p in problems)


def test_every_problem_is_collected_not_just_the_first() -> None:
    """A single run should surface all four mistakes, not stop at the first."""
    with pytest.raises(ConfigError) as exc_info:
        load_settings(
            {
                "LIVEKIT_URL": "http://not-websocket",
                "LIVEKIT_API_KEY": "k",
                "LIVEKIT_API_SECRET": "s",
                "GOOGLE_API_KEY": "g",
                "NINA_TEMPERATURE": "9",
                "NINA_TOOLS": "clock,teleport",
                "NINA_LOG_FORMAT": "yaml",
            }
        )

    problems = exc_info.value.problems
    assert len(problems) == 4
    assert any("ws://" in p for p in problems)
    assert any("NINA_TEMPERATURE" in p for p in problems)
    assert any("teleport" in p for p in problems)
    assert any("NINA_LOG_FORMAT" in p for p in problems)


def test_placeholder_url_is_rejected(base_env: dict[str, str]) -> None:
    env = {**base_env, "LIVEKIT_URL": "wss://<your-livekit-url>"}
    with pytest.raises(ConfigError) as exc_info:
        load_settings(env)
    assert any("placeholder" in p for p in exc_info.value.problems)


def test_require_credentials_false_allows_empty_env() -> None:
    settings = load_settings({}, require_credentials=False)
    assert settings.livekit_url == ""
    assert settings.persona.assistant_name == "NINA"


def test_pipeline_provider_does_not_require_google_key() -> None:
    settings = load_settings(
        {
            "LIVEKIT_URL": "wss://x.livekit.cloud",
            "LIVEKIT_API_KEY": "k",
            "LIVEKIT_API_SECRET": "s",
            "NINA_PROVIDER": "pipeline",
        }
    )
    assert settings.model.provider == PROVIDER_PIPELINE


def test_tavily_requires_a_key(base_env: dict[str, str]) -> None:
    env = {**base_env, "NINA_SEARCH_PROVIDER": "tavily"}
    with pytest.raises(ConfigError) as exc_info:
        load_settings(env)
    assert any("TAVILY_API_KEY" in p for p in exc_info.value.problems)


def test_tavily_key_satisfies_the_requirement(base_env: dict[str, str]) -> None:
    env = {**base_env, "NINA_SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": "tv"}
    assert load_settings(env).search_provider == "tavily"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("clock,weather", ("clock", "weather")),
        ("CLOCK, Memory ", ("clock", "memory")),
        ("clock,clock", ("clock",)),
        ("none", ()),
    ],
)
def test_tool_list_parsing(base_env: dict[str, str], raw: str, expected: tuple[str, ...]) -> None:
    settings = load_settings({**base_env, "NINA_TOOLS": raw})
    assert settings.tools == expected


def test_disabling_memory_tool_disables_the_store(base_env: dict[str, str]) -> None:
    settings = load_settings({**base_env, "NINA_TOOLS": "clock"})
    assert settings.memory.enabled is False


@pytest.mark.parametrize("raw", ["true", "TRUE", "yes", "1", "on"])
def test_bool_true_forms(base_env: dict[str, str], raw: str) -> None:
    assert load_settings({**base_env, "NINA_GREET_ON_START": raw}).persona.greet_on_start


@pytest.mark.parametrize("raw", ["false", "No", "0", "off"])
def test_bool_false_forms(base_env: dict[str, str], raw: str) -> None:
    assert not load_settings({**base_env, "NINA_GREET_ON_START": raw}).persona.greet_on_start


def test_bad_bool_is_reported(base_env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as exc_info:
        load_settings({**base_env, "NINA_GREET_ON_START": "maybe"})
    assert any("boolean" in p for p in exc_info.value.problems)


def test_interests_are_split_and_trimmed(base_env: dict[str, str]) -> None:
    settings = load_settings({**base_env, "NINA_INTERESTS": " chess , cycling ,"})
    assert settings.persona.interests == ("chess", "cycling")


def test_redacted_hides_secrets_but_keeps_shape(base_env: dict[str, str]) -> None:
    redacted = load_settings(base_env).redacted()

    assert redacted["livekit_api_secret"] == "***"
    assert redacted["livekit_api_key"] == "***"
    assert redacted["google_api_key"] == "***"
    assert redacted["tavily_api_key"] == "<unset>"
    # Non-secret values survive intact so the dump stays useful.
    assert redacted["livekit_url"] == "wss://example.livekit.cloud"
    assert redacted["persona.user_name"] == "Shan"


def test_redacted_never_contains_a_real_secret(base_env: dict[str, str]) -> None:
    env = {**base_env, "LIVEKIT_API_SECRET": "super-secret-value"}
    dumped = str(load_settings(env).redacted())
    assert "super-secret-value" not in dumped


def test_tool_enabled_helper(base_env: dict[str, str]) -> None:
    settings = load_settings({**base_env, "NINA_TOOLS": "clock,search"})
    assert settings.tool_enabled("clock")
    assert not settings.tool_enabled("weather")


def test_settings_are_immutable(base_env: dict[str, str]) -> None:
    settings = load_settings(base_env)
    with pytest.raises(AttributeError):
        settings.livekit_url = "wss://other"  # type: ignore[misc]
