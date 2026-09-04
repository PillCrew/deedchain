"""Agent adapters: turn a framework's run output into a deedchain RunResult.

Each adapter is independent and optional — importing this package never pulls in
a third-party dependency. Native ``browser_use`` objects are handled by duck
typing, the Cloud API by stdlib ``urllib``, and anything else by the open
``AgentRun`` JSONL transcript.
"""

from __future__ import annotations

from . import browser_use, browser_use_cloud, transcript

__all__ = ["browser_use", "browser_use_cloud", "transcript"]
