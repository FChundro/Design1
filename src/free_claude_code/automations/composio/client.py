"""Composio client construction and connection/slug verification helpers."""

import importlib
from dataclasses import dataclass
from typing import Any

from loguru import logger

from .config import ComposioSettings
from .slugs import KNOWN_ACTIONS, KNOWN_TRIGGERS


def build_client(settings: ComposioSettings) -> Any:
    """Return an authenticated Composio client.

    ``composio`` is an optional dependency kept out of the project lockfile, so
    it is imported dynamically: the rest of Free Claude Code (and the type
    checker, which runs without it installed) never depends on the SDK being
    present. The returned object is the SDK's ``Composio`` client.
    """

    try:
        composio = importlib.import_module("composio")
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "The Composio SDK is not installed. These automations are optional and "
            "kept out of the project lockfile; install it separately with "
            "`uv pip install composio` (or `pip install composio`)."
        ) from exc

    return composio.Composio(api_key=settings.api_key)


@dataclass(frozen=True)
class VerifyReport:
    """Outcome of :func:`verify`, ready to print or assert on."""

    missing_actions: tuple[str, ...]
    missing_triggers: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_actions and not self.missing_triggers


def verify(client: Any, settings: ComposioSettings) -> VerifyReport:
    """Check that every configured slug resolves against the live account.

    A slug can drift when a toolkit version changes; this surfaces such drift
    before an automation fails mid-event.
    """

    missing_actions = tuple(
        slug for slug in KNOWN_ACTIONS if not _action_exists(client, settings, slug)
    )
    missing_triggers = tuple(
        slug for slug in KNOWN_TRIGGERS if not _trigger_exists(client, slug)
    )
    return VerifyReport(
        missing_actions=missing_actions, missing_triggers=missing_triggers
    )


def _action_exists(client: Any, settings: ComposioSettings, slug: str) -> bool:
    try:
        tools = client.tools.get(user_id=settings.user_id, tools=[slug])
    except Exception as exc:  # network/SDK errors are all treated as "unknown"
        logger.warning("Could not verify action {}: {}", slug, exc)
        return False
    return bool(tools)


def _trigger_exists(client: Any, slug: str) -> bool:
    try:
        client.triggers.get_type(slug=slug)
    except Exception as exc:  # any failure means "cannot verify"
        logger.warning("Could not verify trigger {}: {}", slug, exc)
        return False
    return True


def unwrap(response: Any) -> dict[str, Any]:
    """Normalise a ``ToolExecutionResponse`` into a plain result dict.

    Raises :class:`RuntimeError` when the tool reported failure so callers do not
    silently act on empty data.
    """

    successful = getattr(response, "successful", True)
    error = getattr(response, "error", None)
    data = getattr(response, "data", None)
    if not successful:
        raise RuntimeError(f"Composio tool call failed: {error or 'unknown error'}")
    return data if isinstance(data, dict) else {"data": data}
