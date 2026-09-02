"""Command line entrypoint.

NINA adds a few commands of its own and hands everything else to LiveKit's CLI,
so ``nina dev``, ``nina start``, ``nina console`` and ``nina download-files``
keep working exactly as documented upstream.

Own commands:

``doctor``
    Check configuration and installed dependencies without connecting to
    anything. The fastest way to find out why a worker will not start.
``prompt``
    Print the generated system prompt and greeting instruction.
``memory``
    Inspect or edit the persistent memory store from a terminal.
"""

from __future__ import annotations

import sys
from typing import Any

from . import __version__
from .config import Settings, load_settings
from .errors import ConfigError, NinaError
from .logging_setup import configure_logging
from .memory import MemoryStore
from .persona import build_greeting, build_instructions

OWN_COMMANDS = ("doctor", "prompt", "memory", "version")

USAGE = f"""NINA {__version__} - a realtime voice assistant on LiveKit Agents.

Usage:
  nina dev                 Run a worker in development mode (hot reload)
  nina console             Talk to NINA in the terminal, no LiveKit room needed
  nina start               Run a worker in production mode
  nina download-files      Pre-download model files (do this in your Dockerfile)

  nina doctor              Validate configuration and dependencies
  nina prompt              Print the generated system prompt
  nina memory list         Show saved memories
  nina memory forget KEY   Delete one saved memory
  nina memory clear        Delete all saved memories
  nina version             Print the version

Configuration is read from the environment and from a local .env file.
See .env.example for every supported variable.
"""


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        return
    load_dotenv()


def _print_err(message: str) -> None:
    print(message, file=sys.stderr)


def _check_import(label: str, module: str) -> bool:
    """Report whether an optional runtime dependency is importable."""
    try:
        __import__(module)
    except ImportError as exc:
        print(f"  [MISSING] {label}: {exc}")
        return False
    print(f"  [ok]      {label}")
    return True


def cmd_doctor() -> int:
    """Validate configuration and dependencies. Returns a process exit code."""
    _load_dotenv()
    print(f"NINA {__version__} doctor\n")

    print("Dependencies:")
    deps_ok = all(
        [
            _check_import("livekit-agents", "livekit.agents"),
            _check_import("livekit google plugin", "livekit.plugins.google"),
            _check_import("httpx", "httpx"),
        ]
    )
    _check_import("noise cancellation plugin (optional)", "livekit.plugins.noise_cancellation")
    print()

    print("Configuration:")
    config_ok = True
    settings: Settings | None = None
    try:
        settings = load_settings()
        print("  [ok]      all required settings present and valid")
    except ConfigError as exc:
        config_ok = False
        for problem in exc.problems:
            print(f"  [PROBLEM] {problem}")
        # Fall back to a lenient read so the summary below is still useful.
        try:
            settings = load_settings(require_credentials=False)
        except ConfigError:
            settings = None
    print()

    if settings is not None:
        from . import providers  # noqa: PLC0415 - keeps `doctor` usable without LiveKit

        print("Summary:")
        print(f"  stack:  {providers.describe(settings)}")
        print(f"  tools:  {', '.join(settings.tools) or 'none'}")
        print(f"  memory: {settings.memory.path if settings.memory.enabled else 'disabled'}")
        print(f"  user:   {settings.persona.user_name}")
        print()
        print("Resolved settings (secrets redacted):")
        for key, value in sorted(settings.redacted().items()):
            print(f"  {key} = {value}")
        print()

    if config_ok and deps_ok:
        print("All good. Run `nina console` to talk to NINA locally.")
        return 0
    _print_err("Doctor found problems. Fix the items marked above, then re-run `nina doctor`.")
    return 1


def cmd_prompt() -> int:
    """Print the generated prompts, for prompt-engineering iteration."""
    _load_dotenv()
    settings = load_settings(require_credentials=False)
    print("=== SYSTEM INSTRUCTIONS ===\n")
    print(build_instructions(settings.persona, tools=settings.tools))
    print("\n=== GREETING INSTRUCTION ===\n")
    print(build_greeting(settings.persona))
    return 0


def cmd_memory(argv: list[str]) -> int:
    """Inspect or edit the persistent memory store."""
    _load_dotenv()
    settings = load_settings(require_credentials=False)
    store = MemoryStore(
        settings.memory.path,
        max_items=settings.memory.max_items,
        max_value_chars=settings.memory.max_value_chars,
    )
    store.load()

    action = argv[0] if argv else "list"

    if action == "list":
        items = store.all_items()
        if not items:
            print(f"No memories saved at {settings.memory.path}.")
            return 0
        print(f"{len(items)} memories at {settings.memory.path}:\n")
        for item in items:
            print(f"  {item.key}: {item.value}")
        return 0

    if action == "forget":
        if len(argv) < 2:
            _print_err("usage: nina memory forget KEY")
            return 2
        key = " ".join(argv[1:])
        if store.forget(key):
            print(f"Removed {key}.")
            return 0
        _print_err(f"Nothing saved under {key}.")
        return 1

    if action == "clear":
        count = len(store)
        store.clear()
        print(f"Cleared {count} memories.")
        return 0

    _print_err(f"unknown memory command {action!r}; expected list, forget, or clear")
    return 2


def _delegate_to_livekit() -> int:
    """Hand control to LiveKit's CLI for dev/start/console/download-files."""
    from .runtime import run  # noqa: PLC0415 - imported only when actually running

    run()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch a command. Returns a process exit code."""
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else ""

    if command in ("-h", "--help", "help", ""):
        print(USAGE)
        return 0
    if command in ("version", "--version", "-V"):
        print(f"NINA {__version__}")
        return 0

    # Own commands get plain logging; LiveKit configures its own.
    if command in OWN_COMMANDS:
        configure_logging("WARNING", "text")

    try:
        if command == "doctor":
            return cmd_doctor()
        if command == "prompt":
            return cmd_prompt()
        if command == "memory":
            return cmd_memory(argv[1:])
        return _delegate_to_livekit()
    except ConfigError as exc:
        _print_err(str(exc))
        _print_err("\nRun `nina doctor` for a full check, or see .env.example.")
        return 2
    except NinaError as exc:
        _print_err(f"error: {exc}")
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


def _cli() -> Any:
    sys.exit(main())


if __name__ == "__main__":
    _cli()
