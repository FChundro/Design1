"""External service integrations that are not model providers.

Unlike ``free_claude_code.providers`` (streaming OpenAI/Anthropic-compatible
model backends), integrations here expose self-contained capabilities backed by
third-party APIs. The first is web-grounded question answering via the
Perplexity Agent API.
"""

from free_claude_code.integrations.perplexity_agent import (
    Citation,
    GroundedAnswer,
    SearchSource,
    api_key_present,
    build_client,
    web_grounded_answer,
)

__all__ = [
    "Citation",
    "GroundedAnswer",
    "SearchSource",
    "api_key_present",
    "build_client",
    "web_grounded_answer",
]
