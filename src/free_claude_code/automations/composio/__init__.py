"""Composio-powered automations for Free Claude Code.

These are optional and event-driven: they connect the project's GitHub, chat,
and inbox activity to small handlers via Composio's managed triggers and tools.
Install the extra (``uv pip install -e '.[automations]'``), set the
``COMPOSIO_*`` environment variables (see ``.env.example``), then run:

    python -m free_claude_code.automations.composio run

``verify`` checks that the configured slugs resolve; ``list`` prints the enabled
automations.
"""

from __future__ import annotations

from .actions import Actions
from .client import VerifyReport, build_client, verify
from .config import ComposioSettings, load_settings
from .handlers import AutomationEvent, HandlerResult, dispatch, selected_automations
from .runner import run

__all__ = [
    "Actions",
    "AutomationEvent",
    "ComposioSettings",
    "HandlerResult",
    "VerifyReport",
    "build_client",
    "dispatch",
    "load_settings",
    "run",
    "selected_automations",
    "verify",
]
