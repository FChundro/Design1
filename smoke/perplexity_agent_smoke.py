"""Minimal real-request smoke check for the Perplexity Agent integration.

Run it directly once ``PERPLEXITY_API_KEY`` is exported::

    uv run python -m smoke.perplexity_agent_smoke

It makes one small web-grounded request and prints only the response *shape*
(id, status, model, sizes) plus a short answer preview. It never prints the API
key. A missing key exits non-zero with guidance instead of raising.
"""

import sys
from typing import Any

from free_claude_code.core.failures import ExecutionFailure
from free_claude_code.integrations.perplexity_agent import (
    PERPLEXITY_API_KEY_ENV,
    GroundedAnswer,
    api_key_present,
    web_grounded_answer,
)

DEFAULT_QUERY = "In one sentence, what is the Model Context Protocol?"


def answer_shape(answer: GroundedAnswer) -> dict[str, Any]:
    """Return a key-free, JSON-friendly summary of an answer."""
    return {
        "id": answer.response_id,
        "status": answer.status,
        "model": answer.model,
        "answer_chars": len(answer.text),
        "sources": len(answer.sources),
        "citations": len(answer.citations),
        "usage_present": answer.usage is not None,
    }


def run_smoke(query: str = DEFAULT_QUERY) -> dict[str, Any]:
    """Make one real Agent request and return its shape.

    Raises :class:`ExecutionFailure` on a missing key or any API error.
    """
    answer = web_grounded_answer(query, preset="medium")
    return answer_shape(answer)


def _load_dotenv_if_present() -> None:
    if api_key_present():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    query = args[0] if args else DEFAULT_QUERY

    _load_dotenv_if_present()
    if not api_key_present():
        print(
            f"missing_env: {PERPLEXITY_API_KEY_ENV} is not set.\n"
            "Create a key at https://console.perplexity.ai and export it:\n"
            f"    export {PERPLEXITY_API_KEY_ENV}=pplx-...",
            file=sys.stderr,
        )
        return 1

    try:
        shape = run_smoke(query)
    except ExecutionFailure as failure:
        print(
            f"request_failed: status={failure.status_code} kind={failure.kind} "
            f"retryable={failure.retryable}\n{failure.message}",
            file=sys.stderr,
        )
        return 1

    print("ok: Perplexity Agent request succeeded (HTTP 200).")
    for key, value in shape.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
