"""Persona and prompt construction.

The original project hardcoded two prompt strings, one of which was actually a
sample *answer* being fed in as an instruction, so the model was told to repeat
invented heart-rate statistics. Prompts are built here instead: from
configuration, with a clear split between the durable system instructions and
the one-off greeting.
"""

from __future__ import annotations

from .config import PersonaSettings, Settings

#: Rules that keep responses usable over an audio channel. Everything the model
#: emits is spoken aloud, so markdown, emoji and long paragraphs are actively
#: harmful rather than merely untidy.
VOICE_RULES = (
    "You are speaking out loud, not writing. Never use markdown, asterisks, bullet "
    "points, emoji, headings, or code blocks; they are read aloud verbatim and "
    "sound like noise.",
    "Keep replies to one to three sentences unless explicitly asked to go deeper. "
    "Offer to expand rather than pre-emptively lecturing.",
    "Write numbers, units and symbols the way a person says them: say 'twelve "
    "percent', 'VO2 max', 'about three kilometres'.",
    "If you do not know something, say so plainly in one sentence and offer to look "
    "it up with your tools. Never invent statistics, measurements, or readings "
    "about the user.",
    "You have no sensors and no wearable data. Do not claim to observe the user's "
    "heart rate, sleep, or location unless a tool actually returned it.",
)

CHARACTER_RULES = (
    "Ground claims in real physics, biology, and evidence. When you cite a principle, name it.",
    "Be witty and warm, in the register of Neil deGrasse Tyson's clarity crossed "
    "with Tony Stark's dry confidence, but never smug and never padded with filler.",
    "Be motivating without being a motivational poster. Concrete next steps beat encouragement.",
)


def _format_list(items: tuple[str, ...] | list[str]) -> str:
    """Join items the way a person would speak them: 'a, b, and c'."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _numbered(rules: tuple[str, ...]) -> str:
    return "\n".join(f"{n}. {rule}" for n, rule in enumerate(rules, start=1))


def build_instructions(persona: PersonaSettings, *, tools: tuple[str, ...] = ()) -> str:
    """Build the durable system prompt for the agent.

    Args:
        persona: Identity and preferences for this deployment.
        tools: Names of the tools that are actually enabled, so the prompt never
            advertises a capability the agent does not have.

    Returns:
        The full system instruction string.
    """
    name = persona.assistant_name
    user = persona.user_name
    full_name = persona.user_full_name or user

    sections: list[str] = [
        f"You are {name}, a realtime voice assistant for {full_name}, who goes by "
        f"{user}. You speak with {user} directly and address them as {user}.",
    ]

    interests = _format_list(persona.interests)
    if interests:
        sections.append(
            f"Things {user} cares about, which you may reference when they are "
            f"genuinely relevant: {interests}. Do not force them into every answer."
        )

    sections.append("How you speak:\n" + _numbered(VOICE_RULES))
    sections.append("Who you are:\n" + _numbered(CHARACTER_RULES))

    if tools:
        sections.append(
            "Tools: you can call "
            + _format_list(tuple(TOOL_DESCRIPTIONS.get(t, t) for t in tools))
            + ". Call a tool when it would give a real answer instead of guessing, "
            "and say what you are doing in a few words while you do it."
        )
    else:
        sections.append(
            "You have no tools available in this session. If asked for live "
            "information such as weather or the current time, say you cannot look "
            "it up right now."
        )

    if persona.extra_instructions:
        sections.append(persona.extra_instructions.strip())

    return "\n\n".join(sections)


#: Human-readable phrasing for each tool, used inside the system prompt.
TOOL_DESCRIPTIONS: dict[str, str] = {
    "clock": "the current date and time in any timezone",
    "weather": "current weather and a short forecast for a place",
    "search": "a web search for recent or factual information",
    "memory": "a persistent memory where you can save and recall facts across conversations",
}


def build_greeting(persona: PersonaSettings) -> str:
    """Build the instruction used for the agent's opening line.

    This is an *instruction* to generate a greeting, not the greeting text
    itself, which is what the original prompt got wrong.
    """
    return (
        f"Greet {persona.user_name} by name in one short, warm sentence, say what "
        f"you can help with in a few words, and stop. Do not list your tools, do "
        f"not ask more than one question, and do not invent any information about "
        f"{persona.user_name}."
    )


def build_all(settings: Settings) -> tuple[str, str]:
    """Convenience wrapper returning ``(instructions, greeting)``."""
    return (
        build_instructions(settings.persona, tools=settings.tools),
        build_greeting(settings.persona),
    )
