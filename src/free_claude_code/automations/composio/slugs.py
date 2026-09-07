"""Composio action and trigger slugs used by the automations.

Slugs are defined server-side by Composio and can differ between toolkit
versions and accounts. They are collected here so there is exactly one place to
confirm or override them. Run ``python -m free_claude_code.automations.composio
verify`` to check, against your live Composio account, that every slug below is
spelled correctly and available before relying on it.
"""

from __future__ import annotations

from typing import Final

# --- Toolkits ---------------------------------------------------------------
# Toolkit slugs group actions and triggers; used for connection checks and for
# filtering the trigger subscription.
TOOLKIT_GITHUB: Final = "GITHUB"
TOOLKIT_GMAIL: Final = "GMAIL"
TOOLKIT_DISCORD: Final = "DISCORDBOT"
TOOLKIT_SLACK: Final = "SLACK"

# --- Triggers ---------------------------------------------------------------
# Events that Composio pushes to a subscription. Create one instance per event
# with ``triggers.create(slug, ...)`` and dispatch on ``event.trigger_slug``.
TRIGGER_GITHUB_ISSUE_ADDED: Final = "GITHUB_ISSUE_ADDED_EVENT"
TRIGGER_GITHUB_PULL_REQUEST: Final = "GITHUB_PULL_REQUEST_EVENT"
TRIGGER_GITHUB_WORKFLOW_RUN: Final = "GITHUB_WORKFLOW_RUN_EVENT"
TRIGGER_GITHUB_RELEASE: Final = "GITHUB_RELEASE_EVENT"
TRIGGER_GMAIL_NEW_MESSAGE: Final = "GMAIL_NEW_GMAIL_MESSAGE"

# --- Actions ----------------------------------------------------------------
# Tools invoked with ``tools.execute(slug, arguments, ...)``.
ACTION_GITHUB_CREATE_ISSUE: Final = "GITHUB_CREATE_AN_ISSUE"
ACTION_GITHUB_COMMENT_ISSUE: Final = "GITHUB_CREATE_AN_ISSUE_COMMENT"
ACTION_GITHUB_ADD_LABELS: Final = "GITHUB_ADD_LABELS_TO_AN_ISSUE"
ACTION_GITHUB_LIST_PRS: Final = "GITHUB_LIST_PULL_REQUESTS"
ACTION_GITHUB_LIST_COMMITS: Final = "GITHUB_LIST_COMMITS"
ACTION_GMAIL_SEND: Final = "GMAIL_SEND_EMAIL"
ACTION_DISCORD_SEND: Final = "DISCORDBOT_CREATE_MESSAGE"
ACTION_SLACK_SEND: Final = "SLACK_SENDS_A_MESSAGE_TO_A_SLACK_CHANNEL"


# Every slug this package references, grouped by kind, for the verify command.
KNOWN_TOOLKITS: Final = (
    TOOLKIT_GITHUB,
    TOOLKIT_GMAIL,
    TOOLKIT_DISCORD,
    TOOLKIT_SLACK,
)

KNOWN_TRIGGERS: Final = (
    TRIGGER_GITHUB_ISSUE_ADDED,
    TRIGGER_GITHUB_PULL_REQUEST,
    TRIGGER_GITHUB_WORKFLOW_RUN,
    TRIGGER_GITHUB_RELEASE,
    TRIGGER_GMAIL_NEW_MESSAGE,
)

KNOWN_ACTIONS: Final = (
    ACTION_GITHUB_CREATE_ISSUE,
    ACTION_GITHUB_COMMENT_ISSUE,
    ACTION_GITHUB_ADD_LABELS,
    ACTION_GITHUB_LIST_PRS,
    ACTION_GITHUB_LIST_COMMITS,
    ACTION_GMAIL_SEND,
    ACTION_DISCORD_SEND,
    ACTION_SLACK_SEND,
)
