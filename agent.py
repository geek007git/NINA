#!/usr/bin/env python
"""Launcher kept at the repo root so `python agent.py dev` still works.

The implementation now lives in the `nina` package under `src/`. This shim only
makes the package importable when it has not been installed, then delegates.

Preferred invocation once installed (`pip install -e .`):

    nina dev
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nina.__main__ import main  # noqa: E402  (path setup must run first)

if __name__ == "__main__":
    sys.exit(main())
