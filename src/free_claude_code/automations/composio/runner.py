"""Register the enabled triggers and dispatch their events to the handlers."""

from typing import Any

from loguru import logger

from .actions import Actions
from .client import build_client
from .config import ComposioSettings, load_settings
from .handlers import AutomationEvent, dispatch, selected_automations


def ensure_triggers(client: Any, settings: ComposioSettings) -> set[str]:
    """Create a trigger instance for each distinct trigger the run needs.

    Composio de-duplicates instances per (trigger, connected account), so calling
    this on every start is idempotent. Returns the set of trigger slugs armed.
    """

    slugs_needed = {auto.trigger_slug for auto in selected_automations(settings)}
    for slug in sorted(slugs_needed):
        try:
            client.triggers.create(slug, user_id=settings.user_id)
            logger.info("Armed trigger {}", slug)
        except Exception as exc:  # report but keep arming the rest
            logger.warning("Could not arm trigger {}: {}", slug, exc)
    return slugs_needed


def run(settings: ComposioSettings | None = None) -> None:
    """Arm triggers and block, dispatching events until interrupted."""

    settings = settings or load_settings()
    client = build_client(settings)
    actions = Actions(client, settings)

    armed = ensure_triggers(client, settings)
    if not armed:
        logger.warning("No automations enabled; nothing to do.")
        return

    subscription = client.triggers.subscribe()

    @subscription.handle()
    def _on_event(event: object) -> None:
        automation_event = AutomationEvent.from_trigger_event(event)
        dispatch(automation_event, actions, settings)

    names = ", ".join(auto.name for auto in selected_automations(settings))
    logger.info("Composio automations running: {}", names)
    try:
        subscription.wait_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive stop
        logger.info("Stopping Composio automations.")
        subscription.stop()
