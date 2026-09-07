"""Typed, intention-revealing wrappers over ``composio.tools.execute``.

Each method maps one product action ("create a GitHub issue", "post to the
notification channel") onto a single Composio tool call, so the automation
handlers never touch raw slugs or response envelopes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from . import slugs
from .client import unwrap
from .config import ComposioSettings

if TYPE_CHECKING:
    from composio import Composio


class Actions:
    """Product-level operations bound to one Composio client and settings."""

    def __init__(self, client: Composio, settings: ComposioSettings) -> None:
        self._client = client
        self._settings = settings

    def _execute(self, slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
        logger.debug("Executing Composio action {} with {}", slug, arguments)
        response = self._client.tools.execute(
            slug,
            arguments=arguments,
            user_id=self._settings.user_id,
        )
        return unwrap(response)

    # --- GitHub -------------------------------------------------------------
    def create_issue(
        self, *, title: str, body: str, labels: list[str] | None = None
    ) -> dict[str, Any]:
        owner, repo = self._settings.owner_repo()
        arguments: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "title": title,
            "body": body,
        }
        if labels:
            arguments["labels"] = labels
        return self._execute(slugs.ACTION_GITHUB_CREATE_ISSUE, arguments)

    def comment_on_issue(self, *, issue_number: int, body: str) -> dict[str, Any]:
        owner, repo = self._settings.owner_repo()
        return self._execute(
            slugs.ACTION_GITHUB_COMMENT_ISSUE,
            {"owner": owner, "repo": repo, "issue_number": issue_number, "body": body},
        )

    def add_labels(self, *, issue_number: int, labels: list[str]) -> dict[str, Any]:
        owner, repo = self._settings.owner_repo()
        return self._execute(
            slugs.ACTION_GITHUB_ADD_LABELS,
            {
                "owner": owner,
                "repo": repo,
                "issue_number": issue_number,
                "labels": labels,
            },
        )

    def list_merged_pulls(self, *, per_page: int = 50) -> list[dict[str, Any]]:
        owner, repo = self._settings.owner_repo()
        result = self._execute(
            slugs.ACTION_GITHUB_LIST_PRS,
            {"owner": owner, "repo": repo, "state": "closed", "per_page": per_page},
        )
        pulls = (
            result.get("data")
            if isinstance(result.get("data"), list)
            else result.get("items")
        )
        if not isinstance(pulls, list):
            return []
        return [pr for pr in pulls if isinstance(pr, dict) and pr.get("merged_at")]

    # --- Notifications ------------------------------------------------------
    def notify(self, message: str) -> dict[str, Any] | None:
        """Post ``message`` to the configured chat channel, if any."""

        channel = self._settings.notify_channel
        if channel == "none":
            logger.info("Notifications disabled; would have sent: {}", message)
            return None
        if channel == "discord":
            return self._execute(
                slugs.ACTION_DISCORD_SEND,
                {"channel_id": self._settings.discord_channel_id, "content": message},
            )
        return self._execute(
            slugs.ACTION_SLACK_SEND,
            {"channel": self._settings.slack_channel, "text": message},
        )

    # --- Email --------------------------------------------------------------
    def send_email(self, *, recipient: str, subject: str, body: str) -> dict[str, Any]:
        return self._execute(
            slugs.ACTION_GMAIL_SEND,
            {"recipient_email": recipient, "subject": subject, "body": body},
        )
