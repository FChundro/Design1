"""Live smoke test for the Perplexity Agent integration.

Opt-in: it is skipped unless ``PERPLEXITY_API_KEY`` is configured, and it makes
one real web-grounded request. Like the rest of ``smoke/``, it is excluded from
the default ``pytest`` run (``testpaths = ["tests"]``) and is executed
explicitly, e.g. ``uv run pytest smoke -m live``.
"""

import pytest

from free_claude_code.integrations.perplexity_agent import api_key_present
from smoke.perplexity_agent_smoke import run_smoke

pytestmark = [pytest.mark.live]


def test_perplexity_agent_minimal_request_live() -> None:
    if not api_key_present():
        pytest.skip("missing_env: PERPLEXITY_API_KEY is not configured")

    shape = run_smoke("In one sentence, what is the Model Context Protocol?")

    assert shape["status"] == "completed"
    assert isinstance(shape["id"], str) and shape["id"]
    assert isinstance(shape["answer_chars"], int) and shape["answer_chars"] > 0
