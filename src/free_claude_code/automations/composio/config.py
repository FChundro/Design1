"""Validated settings for the Composio automations, sourced from the environment."""

import os
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

# Environment variable names. Kept as constants so the verify/runner commands and
# tests refer to the same keys.
ENV_API_KEY = "COMPOSIO_API_KEY"
ENV_USER_ID = "COMPOSIO_USER_ID"
ENV_REPO = "COMPOSIO_GITHUB_REPO"
ENV_NOTIFY_CHANNEL = "COMPOSIO_NOTIFY_CHANNEL"
ENV_DISCORD_CHANNEL_ID = "COMPOSIO_DISCORD_CHANNEL_ID"
ENV_SLACK_CHANNEL = "COMPOSIO_SLACK_CHANNEL"
ENV_DIGEST_RECIPIENT = "COMPOSIO_DIGEST_EMAIL"
ENV_INBOX_LABEL = "COMPOSIO_INBOX_ISSUE_LABEL"
ENV_ENABLED = "COMPOSIO_AUTOMATIONS"

NotifyChannel = Literal["discord", "slack", "none"]

# The automation names the runner understands. Ordering is display-only.
ALL_AUTOMATIONS: tuple[str, ...] = (
    "issue_triage",
    "ci_failure",
    "release_notes",
    "inbox_to_issue",
)


def _strip_or_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _split_csv(value: object) -> object:
    if value is None or isinstance(value, (list, tuple)):
        return value
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


OptionalStr = Annotated[str | None, BeforeValidator(_strip_or_none)]


class ComposioSettings(BaseModel):
    """Everything the automations need to run, already validated."""

    model_config = ConfigDict(extra="ignore")

    api_key: str = Field(min_length=1)
    user_id: str = "default"
    repo: OptionalStr = None
    notify_channel: NotifyChannel = "discord"
    discord_channel_id: OptionalStr = None
    slack_channel: OptionalStr = None
    digest_email: OptionalStr = None
    inbox_issue_label: str = "from-inbox"
    enabled: Annotated[list[str], BeforeValidator(_split_csv)] = Field(
        default_factory=lambda: list(ALL_AUTOMATIONS)
    )

    @model_validator(mode="after")
    def _check_notify_target(self) -> ComposioSettings:
        if self.notify_channel == "discord" and not self.discord_channel_id:
            raise ValueError(
                f"{ENV_NOTIFY_CHANNEL}=discord requires {ENV_DISCORD_CHANNEL_ID}."
            )
        if self.notify_channel == "slack" and not self.slack_channel:
            raise ValueError(
                f"{ENV_NOTIFY_CHANNEL}=slack requires {ENV_SLACK_CHANNEL}."
            )
        unknown = [name for name in self.enabled if name not in ALL_AUTOMATIONS]
        if unknown:
            allowed = ", ".join(ALL_AUTOMATIONS)
            raise ValueError(f"Unknown automations {unknown}. Choose from: {allowed}.")
        return self

    def owner_repo(self) -> tuple[str, str]:
        """Split ``owner/name`` into its parts, raising if it is missing."""

        if not self.repo:
            raise ValueError(
                f"{ENV_REPO} is required for GitHub automations (owner/name)."
            )
        owner, separator, name = self.repo.partition("/")
        if not separator or not owner or not name:
            raise ValueError(
                f"{ENV_REPO} must be in 'owner/name' form, got {self.repo!r}."
            )
        return owner, name


def load_settings(env: Mapping[str, str] | None = None) -> ComposioSettings:
    """Build :class:`ComposioSettings` from ``env`` (defaults to ``os.environ``)."""

    source = env if env is not None else os.environ
    data: dict[str, Any] = {
        "api_key": source.get(ENV_API_KEY, ""),
        "user_id": source.get(ENV_USER_ID) or "default",
        "repo": source.get(ENV_REPO),
        "notify_channel": source.get(ENV_NOTIFY_CHANNEL) or "discord",
        "discord_channel_id": source.get(ENV_DISCORD_CHANNEL_ID),
        "slack_channel": source.get(ENV_SLACK_CHANNEL),
        "digest_email": source.get(ENV_DIGEST_RECIPIENT),
        "inbox_issue_label": source.get(ENV_INBOX_LABEL) or "from-inbox",
    }
    # Only override the default automation set when the variable is actually set,
    # so an unset value keeps the full roster rather than clearing it.
    enabled = source.get(ENV_ENABLED)
    if enabled and enabled.strip():
        data["enabled"] = enabled
    return ComposioSettings.model_validate(data)
