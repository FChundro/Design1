"""Unit tests for the Composio automations: config, classification, dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from free_claude_code.automations.composio import slugs
from free_claude_code.automations.composio.config import (
    ALL_AUTOMATIONS,
    ComposioSettings,
    load_settings,
)
from free_claude_code.automations.composio.handlers import (
    AutomationEvent,
    _classify_labels,
    dispatch,
    selected_automations,
)


class RecordingActions:
    """Stand-in for :class:`Actions` that records calls instead of hitting Composio."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def add_labels(self, *, issue_number: int, labels: list[str]) -> dict[str, Any]:
        self.calls.append(
            ("add_labels", {"issue_number": issue_number, "labels": labels})
        )
        return {"labels": labels}

    def notify(self, message: str) -> dict[str, Any]:
        self.calls.append(("notify", {"message": message}))
        return {"ok": True}

    def create_issue(
        self, *, title: str, body: str, labels: list[str] | None = None
    ) -> dict[str, Any]:
        self.calls.append(("create_issue", {"title": title, "labels": labels}))
        return {"number": 321}

    def send_email(self, *, recipient: str, subject: str, body: str) -> dict[str, Any]:
        self.calls.append(("send_email", {"recipient": recipient, "subject": subject}))
        return {"id": "e1"}


def _settings(**overrides: Any) -> ComposioSettings:
    base: dict[str, Any] = {
        "api_key": "k",
        "repo": "FChundro/Design1",
        "notify_channel": "discord",
        "discord_channel_id": "42",
    }
    base.update(overrides)
    return ComposioSettings(**base)


def _kinds(actions: RecordingActions) -> list[str]:
    return [name for name, _ in actions.calls]


# --- config -----------------------------------------------------------------
def test_load_settings_defaults_to_full_roster(monkeypatch):
    monkeypatch.delenv("COMPOSIO_AUTOMATIONS", raising=False)
    monkeypatch.setenv("COMPOSIO_API_KEY", "abc")
    monkeypatch.setenv("COMPOSIO_GITHUB_REPO", "o/r")
    monkeypatch.setenv("COMPOSIO_NOTIFY_CHANNEL", "none")
    settings = load_settings()
    assert settings.enabled == list(ALL_AUTOMATIONS)
    assert settings.user_id == "default"


def test_discord_channel_required_for_discord_notify():
    with pytest.raises(ValueError, match="COMPOSIO_DISCORD_CHANNEL_ID"):
        ComposioSettings(api_key="k", notify_channel="discord")


def test_unknown_automation_rejected():
    with pytest.raises(ValueError, match="Unknown automations"):
        _settings(enabled=["issue_triage", "nope"])


def test_owner_repo_split_and_validation():
    assert _settings().owner_repo() == ("FChundro", "Design1")
    with pytest.raises(ValueError, match="owner/name"):
        _settings(repo="not-a-repo").owner_repo()


def test_enabled_accepts_csv_string():
    assert _settings(enabled="issue_triage, ci_failure").enabled == [
        "issue_triage",
        "ci_failure",
    ]


# --- classification ---------------------------------------------------------
@pytest.mark.parametrize(
    ("title", "body", "expected"),
    [
        ("App crashes on start", "traceback attached", "bug"),
        ("Feature request: dark mode", "would be nice", "enhancement"),
        ("Fix typo in README", "docs", "documentation"),
        ("How do I configure providers?", "", "question"),
        ("Random note", "", "needs-triage"),
    ],
)
def test_classify_labels(title, body, expected):
    assert expected in _classify_labels(title, body)


# --- dispatch / handlers ----------------------------------------------------
def test_selected_automations_filters_and_orders():
    settings = _settings(enabled=["ci_failure", "issue_triage"])
    names = [a.name for a in selected_automations(settings)]
    assert names == ["ci_failure", "issue_triage"]


def test_issue_triage_labels_and_notifies():
    actions = RecordingActions()
    event = AutomationEvent(
        trigger_slug=slugs.TRIGGER_GITHUB_ISSUE_ADDED,
        toolkit_slug=slugs.TOOLKIT_GITHUB,
        payload={
            "issue": {
                "number": 7,
                "title": "Crash on launch",
                "body": "traceback",
                "html_url": "https://x/7",
                "user": {"login": "octocat"},
            }
        },
    )
    results = dispatch(event, actions, _settings())  # type: ignore[arg-type]
    assert _kinds(actions) == ["add_labels", "notify"]
    assert actions.calls[0][1]["labels"] == ["bug"]
    assert results[0].detail.startswith("labelled #7")


def test_ci_failure_only_fires_on_failure():
    settings = _settings()
    passing = AutomationEvent(
        slugs.TRIGGER_GITHUB_WORKFLOW_RUN,
        slugs.TOOLKIT_GITHUB,
        {"workflow_run": {"conclusion": "success", "name": "tests"}},
    )
    failing = AutomationEvent(
        slugs.TRIGGER_GITHUB_WORKFLOW_RUN,
        slugs.TOOLKIT_GITHUB,
        {
            "workflow_run": {
                "conclusion": "failure",
                "name": "tests",
                "head_branch": "main",
            }
        },
    )
    a1 = RecordingActions()
    assert dispatch(passing, a1, settings)[0].skipped is True  # type: ignore[arg-type]
    assert _kinds(a1) == []

    a2 = RecordingActions()
    dispatch(failing, a2, settings)  # type: ignore[arg-type]
    assert _kinds(a2) == ["notify"]


def test_release_notes_emails_when_recipient_set():
    settings = _settings(digest_email="chundro@gmail.com")
    event = AutomationEvent(
        slugs.TRIGGER_GITHUB_RELEASE,
        slugs.TOOLKIT_GITHUB,
        {"action": "published", "release": {"tag_name": "v1.2.3", "body": "notes"}},
    )
    actions = RecordingActions()
    dispatch(event, actions, settings)  # type: ignore[arg-type]
    assert _kinds(actions) == ["notify", "send_email"]


def test_inbox_to_issue_requires_label():
    settings = _settings(inbox_issue_label="to-triage")
    unlabelled = AutomationEvent(
        slugs.TRIGGER_GMAIL_NEW_MESSAGE,
        slugs.TOOLKIT_GMAIL,
        {"subject": "hi", "label_ids": ["INBOX"]},
    )
    labelled = AutomationEvent(
        slugs.TRIGGER_GMAIL_NEW_MESSAGE,
        slugs.TOOLKIT_GMAIL,
        {"subject": "Bug from user", "sender": "u@x", "label_ids": ["to-triage"]},
    )
    a1 = RecordingActions()
    assert dispatch(unlabelled, a1, settings)[0].skipped is True  # type: ignore[arg-type]

    a2 = RecordingActions()
    dispatch(labelled, a2, settings)  # type: ignore[arg-type]
    assert _kinds(a2) == ["create_issue", "notify"]


def test_dispatch_ignores_non_matching_trigger():
    actions = RecordingActions()
    event = AutomationEvent("SOME_OTHER_TRIGGER", "GITHUB", {})
    assert dispatch(event, actions, _settings()) == []  # type: ignore[arg-type]


def test_handler_error_is_isolated():
    class Boom(RecordingActions):
        def add_labels(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("boom")

    event = AutomationEvent(
        slugs.TRIGGER_GITHUB_ISSUE_ADDED,
        slugs.TOOLKIT_GITHUB,
        {"issue": {"number": 1, "title": "x", "body": "y"}},
    )
    results = dispatch(event, Boom(), _settings(enabled=["issue_triage"]))  # type: ignore[arg-type]
    assert results[0].detail.startswith("error:")
