"""How the harness reaches the agent under test.

An agent is any callable `agent(message, context)` that returns an AgentReply,
a dict with the same keys, or a plain string. `context` carries `case_id` and
`customer_name`.

Two ways to plug one in:
- `load_agent("package.module:attribute")` imports a callable.
- `ReplayAgent(path)` replays replies recorded elsewhere (one JSON object per
  line with `id` and `text`, optionally `intent`, `actions`, `escalate`). Use it
  when the real agent runs somewhere the harness cannot call.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Callable

from .models import AgentReply

Agent = Callable[[str, dict[str, Any]], Any]


class AgentLoadError(ValueError):
    pass


def load_agent(spec: str) -> Agent:
    module_name, sep, attr = spec.partition(":")
    if not sep or not module_name or not attr:
        raise AgentLoadError(f"agent spec '{spec}' must look like package.module:callable")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise AgentLoadError(f"cannot import '{module_name}': {exc}") from exc
    agent = getattr(module, attr, None)
    if not callable(agent):
        raise AgentLoadError(f"'{attr}' in '{module_name}' is missing or not callable")
    return agent


class ReplayAgent:
    """Serves recorded replies by case id."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._replies: dict[str, AgentReply] = {}
        for line_no, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                self._replies[str(record["id"])] = AgentReply.coerce(record)
            except (ValueError, KeyError, TypeError) as exc:
                raise AgentLoadError(f"{self.path}: line {line_no}: {exc}") from exc

    def __call__(self, message: str, context: dict[str, Any]) -> AgentReply:
        case_id = context.get("case_id")
        if case_id not in self._replies:
            raise KeyError(f"no recorded reply for case '{case_id}'")
        return self._replies[case_id]
