"""Composio client construction and connection/slug verification helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from .config import ComposioSettings
from .slugs import KNOWN_ACTIONS, KNOWN_TRIGGERS

if TYPE_CHECKING:
    from composio import Composio


def build_client(settings: ComposioSettings) -> Composio:
    """Return an authenticated Composio client.

    ``composio`` is an optional dependency; import it lazily so the rest of Free
    Claude Code keeps working when the automations extra is not installed.
    """

    try:
        from composio import Composio
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "The Composio SDK is not installed. Install the automations extra: "
            "`uv pip install -e '.[automations]'` (or `pip install composio`)."
        ) from exc

    return Composio(api_key=settings.api_key)


@dataclass(frozen=True)
class VerifyReport:
    """Outcome of :func:`verify`, ready to print or assert on."""

    missing_actions: tuple[str, ...]
    missing_triggers: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_actions and not self.missing_triggers


def verify(client: Composio, settings: ComposioSettings) -> VerifyReport:
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


def _action_exists(client: Composio, settings: ComposioSettings, slug: str) -> bool:
    try:
        tools = client.tools.get(user_id=settings.user_id, tools=[slug])
    except Exception as exc:  # network/SDK errors are all treated as "unknown"
        logger.warning("Could not verify action {}: {}", slug, exc)
        return False
    return bool(tools)


def _trigger_exists(client: Composio, slug: str) -> bool:
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
