"""The command line interface.

``doctor`` in particular is the command people reach for when nothing works, so
it must never raise, whatever the environment looks like.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nina import __version__
from nina.__main__ import main


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run every CLI test against a clean environment and a temp memory path.

    Without this, a developer's own .env would change the results.
    """
    monkeypatch.setattr("nina.__main__._load_dotenv", lambda: None)
    for key in list(_ENV_KEYS):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NINA_MEMORY_PATH", str(tmp_path / "memory.json"))


_ENV_KEYS = (
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "GOOGLE_API_KEY",
    "TAVILY_API_KEY",
    "NINA_PROVIDER",
    "NINA_TOOLS",
    "NINA_SEARCH_PROVIDER",
    "NINA_MEMORY_PATH",
)


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "k")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s")
    monkeypatch.setenv("GOOGLE_API_KEY", "g")


def test_help_lists_the_commands(capsys: Any) -> None:
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "nina doctor" in out
    assert "nina console" in out


def test_no_arguments_shows_help(capsys: Any) -> None:
    assert main([]) == 0
    assert "Usage:" in capsys.readouterr().out


def test_version(capsys: Any) -> None:
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_doctor_fails_on_an_empty_environment(capsys: Any) -> None:
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "[PROBLEM]" in out
    assert "LIVEKIT_URL" in out


def test_doctor_still_prints_a_summary_when_config_is_broken(capsys: Any) -> None:
    """Half-configured is the common case; the summary must survive it."""
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "Summary:" in out
    assert "Resolved settings" in out


def test_doctor_redacts_secrets(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("LIVEKIT_API_SECRET", "do-not-leak-me")
    main(["doctor"])
    out = capsys.readouterr().out
    assert "do-not-leak-me" not in out
    assert "livekit_api_secret = ***" in out


def test_doctor_reports_configuration_valid(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    _configure(monkeypatch)
    main(["doctor"])
    assert "all required settings present and valid" in capsys.readouterr().out


def test_prompt_prints_both_prompts(capsys: Any) -> None:
    assert main(["prompt"]) == 0
    out = capsys.readouterr().out
    assert "=== SYSTEM INSTRUCTIONS ===" in out
    assert "=== GREETING INSTRUCTION ===" in out
    assert "NINA" in out


def test_prompt_works_without_credentials(capsys: Any) -> None:
    """Prompt iteration should not require a LiveKit account."""
    assert main(["prompt"]) == 0


def test_memory_list_when_empty(capsys: Any) -> None:
    assert main(["memory", "list"]) == 0
    assert "No memories saved" in capsys.readouterr().out


def test_memory_roundtrip(capsys: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from nina.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.json")
    store.remember("album", "Kind of Blue")

    assert main(["memory", "list"]) == 0
    assert "album: Kind of Blue" in capsys.readouterr().out

    assert main(["memory", "forget", "album"]) == 0
    assert main(["memory", "list"]) == 0
    assert "No memories saved" in capsys.readouterr().out


def test_memory_forget_missing_key_returns_error(capsys: Any) -> None:
    assert main(["memory", "forget", "nope"]) == 1


def test_memory_forget_without_a_key_is_a_usage_error() -> None:
    assert main(["memory", "forget"]) == 2


def test_memory_clear(tmp_path: Path, capsys: Any) -> None:
    from nina.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.json")
    store.remember("a", "1")

    assert main(["memory", "clear"]) == 0
    assert "Cleared 1 memories" in capsys.readouterr().out


def test_unknown_memory_subcommand_is_a_usage_error() -> None:
    assert main(["memory", "explode"]) == 2


def test_bad_config_on_a_run_command_exits_with_a_readable_message(capsys: Any) -> None:
    """`nina dev` with no config should explain itself, not raise a traceback."""
    assert main(["dev"]) == 2
    err = capsys.readouterr().err
    assert "Invalid NINA configuration" in err
    assert "nina doctor" in err
