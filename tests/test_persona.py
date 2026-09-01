"""Prompt construction.

These tests pin the properties that actually make a voice agent behave: no
markdown, no invented sensor data, and no advertising tools it does not have.
"""

from __future__ import annotations

from nina.config import PersonaSettings, Settings
from nina.persona import build_all, build_greeting, build_instructions


def test_instructions_name_the_assistant_and_the_user() -> None:
    text = build_instructions(PersonaSettings())
    assert "NINA" in text
    assert "Shan" in text
    assert "Shanmuga Priyan" in text


def test_persona_is_configurable() -> None:
    persona = PersonaSettings(
        assistant_name="Atlas",
        user_name="Rae",
        user_full_name="Rae Okonkwo",
        interests=("rock climbing",),
    )
    text = build_instructions(persona)
    assert "Atlas" in text
    assert "Rae Okonkwo" in text
    assert "rock climbing" in text
    assert "Shan" not in text


def test_instructions_ban_markdown_and_emoji() -> None:
    text = build_instructions(PersonaSettings()).lower()
    assert "markdown" in text
    assert "emoji" in text


def test_instructions_forbid_inventing_biometric_data() -> None:
    """The original prompt fed a fake heart-rate reading in as an instruction."""
    text = build_instructions(PersonaSettings()).lower()
    assert "heart rate" in text
    assert "no sensors" in text


def test_enabled_tools_are_described() -> None:
    text = build_instructions(PersonaSettings(), tools=("weather", "memory"))
    assert "weather" in text.lower()
    assert "memory" in text.lower()


def test_no_tools_means_the_prompt_says_so() -> None:
    text = build_instructions(PersonaSettings(), tools=())
    assert "no tools available" in text
    assert "Tools: you can call" not in text


def test_disabled_tool_is_not_advertised() -> None:
    text = build_instructions(PersonaSettings(), tools=("clock",))
    assert "current date and time" in text
    assert "web search" not in text.lower()


def test_extra_instructions_are_appended() -> None:
    persona = PersonaSettings(extra_instructions="Always answer in metric units.")
    assert "Always answer in metric units." in build_instructions(persona)


def test_interest_list_reads_naturally() -> None:
    persona = PersonaSettings(interests=("a", "b", "c"))
    assert "a, b, and c" in build_instructions(persona)

    persona_two = PersonaSettings(interests=("a", "b"))
    assert "a and b" in build_instructions(persona_two)

    persona_one = PersonaSettings(interests=("a",))
    text = build_instructions(persona_one)
    assert "relevant: a." in text


def test_greeting_is_an_instruction_not_a_script() -> None:
    """It must tell the model to greet, not hand it words to parrot."""
    greeting = build_greeting(PersonaSettings())
    assert greeting.startswith("Greet Shan")
    assert "do not invent" in greeting.lower()
    # No fabricated statistics, unlike the original AGENT_RESPONSE constant.
    assert "percent" not in greeting.lower()


def test_build_all_returns_both_prompts() -> None:
    instructions, greeting = build_all(Settings())
    assert "NINA" in instructions
    assert "Greet" in greeting
