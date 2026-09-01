"""Tool guarding and dependency wiring.

:mod:`nina.agent` imports LiveKit lazily, so these tests run without the agent
framework installed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from conftest import run
from nina.agent import ToolDeps, guard
from nina.config import Settings
from nina.errors import NinaError, ToolError
from nina.memory import MemoryStore, NullMemoryStore


def test_guard_passes_success_through() -> None:
    @guard("demo")
    async def ok() -> str:
        return "fine"

    assert run(ok()) == "fine"


def test_guard_converts_tool_error_into_a_spoken_sentence() -> None:
    """A raised tool error would end the call; the text can just be read out."""

    @guard("demo")
    async def fails() -> str:
        raise ToolError("I could not find that place")

    assert run(fails()) == "I could not find that place"


def test_guard_converts_other_nina_errors() -> None:
    @guard("demo")
    async def fails() -> str:
        raise NinaError("disk on fire")

    assert run(fails()) == "I hit a problem with that: disk on fire"


def test_guard_swallows_unexpected_exceptions() -> None:
    @guard("demo")
    async def explodes() -> str:
        raise ZeroDivisionError("boom")

    assert run(explodes()) == "Something went wrong on my side with that one."


def test_guard_logs_unexpected_exceptions(caplog: object) -> None:
    @guard("demo")
    async def explodes() -> str:
        raise ZeroDivisionError("boom")

    with caplog.at_level(logging.ERROR, logger="nina.agent"):  # type: ignore[attr-defined]
        run(explodes())

    assert "tool crashed" in caplog.text  # type: ignore[attr-defined]


def test_guard_preserves_the_signature_and_docstring() -> None:
    """LiveKit builds the tool schema from these, so they must survive."""

    @guard("demo")
    async def documented(context: object, location: str) -> str:
        """Look up a thing.

        Args:
            location: Where to look.
        """
        return location

    import inspect

    assert documented.__name__ == "documented"
    assert documented.__doc__ is not None
    assert "Look up a thing." in documented.__doc__
    assert list(inspect.signature(documented).parameters) == ["context", "location"]


def test_guard_forwards_arguments() -> None:
    @guard("demo")
    async def echo(a: str, b: str = "b") -> str:
        return a + b

    assert run(echo("a")) == "ab"
    assert run(echo("a", b="c")) == "ac"


def test_tool_deps_builds_a_real_store_when_memory_is_on(tmp_path: Path) -> None:
    settings = Settings().with_overrides()
    settings = settings.with_overrides(
        memory=settings.memory.__class__(enabled=True, path=tmp_path / "m.json")
    )
    deps = ToolDeps.from_settings(settings)
    assert isinstance(deps.memory, MemoryStore)
    assert not isinstance(deps.memory, NullMemoryStore)


def test_tool_deps_builds_a_null_store_when_memory_is_off(tmp_path: Path) -> None:
    settings = Settings()
    settings = settings.with_overrides(
        memory=settings.memory.__class__(enabled=False, path=tmp_path / "m.json")
    )
    deps = ToolDeps.from_settings(settings)
    assert isinstance(deps.memory, NullMemoryStore)


def test_tool_deps_close_closes_the_http_client(tmp_path: Path) -> None:
    from conftest import FakeHttp

    http = FakeHttp({})
    deps = ToolDeps(settings=Settings(), http=http, memory=NullMemoryStore())
    run(deps.aclose())
    assert http.closed is True


# --- tool registration ----------------------------------------------------
#
# These exercise build_tools() with the LiveKit loaders faked out, so the
# registration logic is covered without installing the agent framework.


class _FakeRunContext:
    """Stands in for livekit.agents.RunContext."""


def _fake_livekit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make compat return a pass-through function_tool and a dummy RunContext."""
    monkeypatch.setattr("nina.compat.load_function_tool", lambda: (lambda fn: fn))
    monkeypatch.setattr("nina.compat.load_run_context", lambda: _FakeRunContext)


def _deps(settings: Settings) -> ToolDeps:
    from conftest import FakeHttp

    return ToolDeps(settings=settings, http=FakeHttp({}), memory=NullMemoryStore())


def test_all_tools_are_registered_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from nina.agent import build_tools

    _fake_livekit(monkeypatch)
    names = {t.__name__ for t in build_tools(_deps(Settings()))}
    assert names == {
        "get_current_time",
        "get_weather",
        "search_web",
        "remember",
        "recall",
        "forget",
        "list_memories",
    }


def test_disabled_tools_are_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    from nina.agent import build_tools

    _fake_livekit(monkeypatch)
    settings = Settings().with_overrides(tools=("clock",))
    names = {t.__name__ for t in build_tools(_deps(settings))}
    assert names == {"get_current_time"}


def test_search_provider_none_removes_the_search_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from nina.agent import build_tools

    _fake_livekit(monkeypatch)
    settings = Settings().with_overrides(tools=("search",), search_provider="none")
    assert build_tools(_deps(settings)) == []


def test_registered_tool_annotations_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    """LiveKit resolves these with get_type_hints; a NameError here breaks startup.

    The module uses `from __future__ import annotations`, so the RunContext name
    must be resolvable in nina.agent's globals rather than only as a local.
    """
    import typing

    from nina.agent import build_tools

    _fake_livekit(monkeypatch)
    for tool in build_tools(_deps(Settings())):
        hints = typing.get_type_hints(tool)
        assert hints["return"] is str
        assert hints.get("context") is _FakeRunContext or "context" not in hints


def test_registered_tools_have_docstrings_for_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The docstring is the schema description the LLM sees."""
    from nina.agent import build_tools

    _fake_livekit(monkeypatch)
    for tool in build_tools(_deps(Settings())):
        assert tool.__doc__ and len(tool.__doc__.strip()) > 20


def test_memory_tools_operate_on_the_injected_store(monkeypatch: pytest.MonkeyPatch) -> None:
    from nina.agent import build_tools

    _fake_livekit(monkeypatch)
    deps = _deps(Settings().with_overrides(tools=("memory",)))
    tools = {t.__name__: t for t in build_tools(deps)}

    assert "Saved that under album" in run(tools["remember"](None, "album", "Kind of Blue"))
    assert "Kind of Blue" in run(tools["recall"](None, "album"))
    assert "album" in run(tools["list_memories"](None))
    assert "Removed album" in run(tools["forget"](None, "album"))
    assert "nothing saved" in run(tools["recall"](None, "album"))


def test_remember_rejects_empty_input_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nina.agent import build_tools

    _fake_livekit(monkeypatch)
    deps = _deps(Settings().with_overrides(tools=("memory",)))
    tools = {t.__name__: t for t in build_tools(deps)}
    assert "cannot be empty" in run(tools["remember"](None, "  ", "value"))
