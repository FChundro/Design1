"""The automation handlers and the registry that maps triggers to them.

Handlers are deliberately pure with respect to Composio: each takes a decoded
:class:`AutomationEvent` and an :class:`Actions` facade, so they can be unit
tested with a fake ``Actions`` and a hand-built payload.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger

from . import slugs
from .config import ComposioSettings


class SupportsActions(Protocol):
    """The subset of :class:`~.actions.Actions` the handlers depend on.

    Typing against this Protocol keeps handlers decoupled from the concrete
    ``Actions`` (and lets tests pass a lightweight recording fake).
    """

    def add_labels(self, *, issue_number: int, labels: list[str]) -> dict[str, Any]: ...

    def notify(self, message: str) -> dict[str, Any] | None: ...

    def create_issue(
        self, *, title: str, body: str, labels: list[str] | None = None
    ) -> dict[str, Any]: ...

    def send_email(
        self, *, recipient: str, subject: str, body: str
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AutomationEvent:
    """A Composio trigger event, reduced to what the handlers care about."""

    trigger_slug: str
    toolkit_slug: str
    payload: Mapping[str, Any]

    @classmethod
    def from_trigger_event(cls, event: Any) -> AutomationEvent:
        """Adapt a Composio ``TriggerEvent`` into an :class:`AutomationEvent`."""

        payload = getattr(event, "payload", None)
        return cls(
            trigger_slug=getattr(event, "trigger_slug", "") or "",
            toolkit_slug=getattr(event, "toolkit_slug", "") or "",
            payload=payload if isinstance(payload, Mapping) else {},
        )


@dataclass(frozen=True)
class HandlerResult:
    """What a handler did, for logging and tests."""

    automation: str
    skipped: bool = False
    detail: str = ""


HandlerFn = Callable[
    [AutomationEvent, SupportsActions, ComposioSettings], HandlerResult
]


@dataclass(frozen=True)
class Automation:
    """One named automation: the trigger it needs and the handler to run."""

    name: str
    trigger_slug: str
    handler: HandlerFn


def _dig(payload: Mapping[str, Any], *path: str) -> Any:
    """Walk nested mappings by key, returning ``None`` on any miss."""

    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _classify_labels(title: str, body: str) -> list[str]:
    """Heuristically pick issue labels from its wording."""

    text = f"{title}\n{body}".lower()
    rules = {
        "bug": ("bug", "error", "crash", "traceback", "exception", "broken", "fails"),
        "enhancement": (
            "feature",
            "request",
            "add support",
            "would be nice",
            "proposal",
        ),
        "documentation": ("docs", "documentation", "readme", "typo"),
        "question": ("question", "how do i", "how to", "help"),
    }
    labels = [
        label for label, needles in rules.items() if any(n in text for n in needles)
    ]
    return labels or ["needs-triage"]


def handle_issue_triage(
    event: AutomationEvent, actions: SupportsActions, settings: ComposioSettings
) -> HandlerResult:
    """Label a new issue and announce it in the notification channel."""

    issue = _dig(event.payload, "issue") or event.payload
    number = issue.get("number") if isinstance(issue, Mapping) else None
    if not isinstance(number, int):
        return HandlerResult(
            "issue_triage", skipped=True, detail="no issue number in payload"
        )

    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    url = str(issue.get("html_url") or "")
    author = str(_dig(issue, "user", "login") or "someone")

    labels = _classify_labels(title, body)
    actions.add_labels(issue_number=number, labels=labels)
    actions.notify(
        f":inbox_tray: New issue #{number} from **{author}**: {title}\n"
        f"Labelled `{', '.join(labels)}` · {url}".strip()
    )
    return HandlerResult("issue_triage", detail=f"labelled #{number} {labels}")


def handle_ci_failure(
    event: AutomationEvent, actions: SupportsActions, settings: ComposioSettings
) -> HandlerResult:
    """Alert the channel when a workflow run finishes in failure."""

    run = _dig(event.payload, "workflow_run") or event.payload
    conclusion = (
        str(run.get("conclusion") or "").lower() if isinstance(run, Mapping) else ""
    )
    if conclusion not in {"failure", "timed_out", "startup_failure"}:
        return HandlerResult(
            "ci_failure", skipped=True, detail=f"conclusion={conclusion!r}"
        )

    name = str(run.get("name") or "workflow")
    branch = str(run.get("head_branch") or "?")
    url = str(run.get("html_url") or "")
    actions.notify(
        f":rotating_light: CI **{name}** {conclusion} on `{branch}`\n{url}".strip()
    )
    return HandlerResult("ci_failure", detail=f"alerted {name}/{branch}")


def handle_release_notes(
    event: AutomationEvent, actions: SupportsActions, settings: ComposioSettings
) -> HandlerResult:
    """Announce a published release and optionally email the notes."""

    release = _dig(event.payload, "release") or event.payload
    if not isinstance(release, Mapping):
        return HandlerResult(
            "release_notes", skipped=True, detail="no release in payload"
        )
    action = str(event.payload.get("action") or "published")
    if action not in {"published", "released", "created"}:
        return HandlerResult("release_notes", skipped=True, detail=f"action={action!r}")

    tag = str(release.get("tag_name") or release.get("name") or "release")
    url = str(release.get("html_url") or "")
    notes = str(release.get("body") or "").strip()
    actions.notify(f":package: Released **{tag}** · {url}".strip())
    if settings.digest_email and notes:
        actions.send_email(
            recipient=settings.digest_email,
            subject=f"Release {tag}",
            body=f"{notes}\n\n{url}",
        )
    return HandlerResult("release_notes", detail=f"announced {tag}")


def handle_inbox_to_issue(
    event: AutomationEvent, actions: SupportsActions, settings: ComposioSettings
) -> HandlerResult:
    """Turn a labelled inbox email into a GitHub issue."""

    message = event.payload
    label_names = _dig(message, "label_ids") or _dig(message, "labelIds") or []
    if isinstance(label_names, str):
        label_names = [label_names]
    wanted = settings.inbox_issue_label.lower()
    if not any(wanted in str(name).lower() for name in label_names):
        return HandlerResult("inbox_to_issue", skipped=True, detail="label not present")

    subject = str(message.get("subject") or message.get("snippet") or "Inbox item")
    sender = str(message.get("sender") or message.get("from") or "unknown")
    snippet = str(message.get("messageText") or message.get("snippet") or "")
    created = actions.create_issue(
        title=subject,
        body=f"Filed automatically from an inbox email from **{sender}**.\n\n{snippet}",
        labels=[settings.inbox_issue_label],
    )
    number = created.get("number") if isinstance(created, Mapping) else None
    actions.notify(f":email: Filed inbox email from {sender} as issue #{number}.")
    return HandlerResult("inbox_to_issue", detail=f"created issue #{number}")


# Registry ------------------------------------------------------------------
_REGISTRY: dict[str, Automation] = {
    "issue_triage": Automation(
        "issue_triage", slugs.TRIGGER_GITHUB_ISSUE_ADDED, handle_issue_triage
    ),
    "ci_failure": Automation(
        "ci_failure", slugs.TRIGGER_GITHUB_WORKFLOW_RUN, handle_ci_failure
    ),
    "release_notes": Automation(
        "release_notes", slugs.TRIGGER_GITHUB_RELEASE, handle_release_notes
    ),
    "inbox_to_issue": Automation(
        "inbox_to_issue", slugs.TRIGGER_GMAIL_NEW_MESSAGE, handle_inbox_to_issue
    ),
}


def selected_automations(settings: ComposioSettings) -> list[Automation]:
    """Return the enabled automations in registry order."""

    return [_REGISTRY[name] for name in settings.enabled if name in _REGISTRY]


def dispatch(
    event: AutomationEvent, actions: SupportsActions, settings: ComposioSettings
) -> list[HandlerResult]:
    """Run every enabled automation whose trigger matches ``event``."""

    results: list[HandlerResult] = []
    for automation in selected_automations(settings):
        if automation.trigger_slug != event.trigger_slug:
            continue
        try:
            result = automation.handler(event, actions, settings)
        except Exception as exc:  # one bad handler must not kill the loop
            logger.exception("Automation {} failed: {}", automation.name, exc)
            results.append(HandlerResult(automation.name, detail=f"error: {exc}"))
            continue
        logger.info("Automation {}: {}", automation.name, result.detail or "done")
        results.append(result)
    return results
