# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
nina doctor
```

## Before opening a PR

```bash
ruff format .
ruff check .
mypy
pytest
```

Or `make check`.

## How the code is organised

The one rule worth preserving: **LiveKit is imported in as few places as
possible.** `compat.py`, `providers.py` and `runtime.py` know about the agent
framework; `config.py`, `persona.py`, `memory.py` and `tools/` do not, and that
is why the test suite runs in seconds without API keys or network access.

If you find yourself importing `livekit` into a new module, consider whether the
logic belongs in a plain function that `agent.py` can wrap instead.

## Adding a tool

1. Write the logic in `src/nina/tools/<name>.py` as a plain async function that
   takes its inputs plus an `AsyncHttpClient` if it needs the network, and
   returns a short string a person could say out loud. Raise `ToolError` for
   anything the user should hear about.
2. Add the name to `ALL_TOOLS` in `config.py` and a phrase to `TOOL_DESCRIPTIONS`
   in `persona.py`, so the prompt describes it accurately.
3. Register it in `build_tools()` in `agent.py`, wrapped in `@guard(...)`. The
   docstring becomes the schema the model sees — write it for the model, with an
   `Args:` section, and say when *not* to call it.
4. Test it in `tests/test_tools.py` using the `FakeHttp` fake from `conftest.py`.
   No test may touch the network.

## Style

- Type annotations everywhere; `mypy` runs in strict mode.
- Docstrings explain *why*, not *what* — the code says what.
- Anything spoken aloud gets written the way a person says it: no markdown, no
  symbols, no leading zeros in times.
