"""Web-grounded answers via the Perplexity Agent API (``POST /v1/agent``).

This is a self-contained capability, not a streaming model provider: it returns
one grounded answer with its web sources and citations rather than proxying an
SSE stream. It wraps the official ``perplexity`` SDK
(``from perplexity import Perplexity``), whose ``responses`` resource targets the
Agent endpoint (``/v1/responses`` is the OpenAI-compatible alias of ``/v1/agent``).

``perplexityai`` is an *optional* dependency, handled the same way the project
handles ``torch``/``librosa``/``riva``: it is imported lazily inside the
functions that need it, so importing this module never requires the SDK. Install
it with ``uv pip install perplexityai`` (or add it to the project and relock)
before using :func:`web_grounded_answer`.

The API key is a secret. It is resolved from the ``PERPLEXITY_API_KEY``
environment variable and is never logged, printed, or embedded in error
messages. If it is missing, create one at https://console.perplexity.ai and
export it in your shell.

SDK failures are mapped onto the project's canonical
:class:`~free_claude_code.core.failures.ExecutionFailure`, so callers handle
Perplexity errors the same way they handle provider errors. The SDK already
retries transient rate-limit and server errors with backoff (honoring
``Retry-After``); when those retries are exhausted the mapped failure carries
the retry hint in its message.
"""

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from free_claude_code.core.failures import ExecutionFailure, FailureKind

PERPLEXITY_API_KEY_ENV = "PERPLEXITY_API_KEY"

# When neither a model nor a preset is given, fall back to a balanced preset.
# Presets bundle model, tools, and limits, so they are the safest default and do
# not pin a model id that Perplexity may rotate.
DEFAULT_PRESET = "medium"
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_S = 60.0

# Ready-made tool specs. Web grounding is itself a tool; a caller may also pass
# arbitrary tool dicts (for example the code-execution ``sandbox`` tool).
WEB_SEARCH_TOOL: dict[str, str] = {"type": "web_search"}
FETCH_URL_TOOL: dict[str, str] = {"type": "fetch_url"}
FINANCE_SEARCH_TOOL: dict[str, str] = {"type": "finance_search"}


@dataclass(frozen=True, slots=True)
class Citation:
    """One inline URL citation attached to answer text."""

    url: str | None
    title: str | None
    start_index: int | None
    end_index: int | None


@dataclass(frozen=True, slots=True)
class SearchSource:
    """One web source the answer was grounded in."""

    url: str | None
    title: str | None
    snippet: str | None
    date: str | None
    last_updated: str | None
    source: str | None


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    """A parsed Agent API answer with its grounding metadata.

    ``response_id`` can be replayed as ``previous_response_id`` to continue the
    conversation across turns.
    """

    text: str
    response_id: str
    status: str
    model: str
    citations: tuple[Citation, ...]
    sources: tuple[SearchSource, ...]
    usage: Mapping[str, Any] | None


def api_key_present(env: Mapping[str, str] | None = None) -> bool:
    """Return whether ``PERPLEXITY_API_KEY`` is set and non-empty.

    Presence is checked without reading or exposing the value.
    """
    source = env if env is not None else os.environ
    return bool(source.get(PERPLEXITY_API_KEY_ENV, "").strip())


def _resolve_api_key(api_key: str | None) -> str:
    resolved = (
        api_key if api_key is not None else os.environ.get(PERPLEXITY_API_KEY_ENV)
    )
    resolved = (resolved or "").strip()
    if not resolved:
        raise ExecutionFailure(
            kind=FailureKind.AUTHENTICATION,
            status_code=401,
            message=(
                f"{PERPLEXITY_API_KEY_ENV} is not set. Create a key at "
                "https://console.perplexity.ai and export it in your shell."
            ),
            retryable=False,
        )
    return resolved


def build_client(
    *,
    api_key: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Any:
    """Construct a Perplexity SDK client with the resolved key.

    The ``perplexity`` import is deferred so importing this module never requires
    the optional SDK to be installed until a client is actually built.
    """
    resolved = _resolve_api_key(api_key)
    try:
        from perplexity import Perplexity
    except ImportError as exc:
        raise ImportError(
            "The 'perplexityai' package is required for the Perplexity Agent "
            "integration. Install it with: uv pip install perplexityai"
        ) from exc

    return Perplexity(api_key=resolved, max_retries=max_retries, timeout=timeout)


def web_grounded_answer(
    query: str,
    *,
    model: str | None = None,
    preset: str | None = None,
    enable_web_search: bool = True,
    tools: Sequence[Mapping[str, object]] | None = None,
    response_format: Mapping[str, object] | None = None,
    previous_response_id: str | None = None,
    instructions: str | None = None,
    max_output_tokens: int | None = None,
    client: Any | None = None,
) -> GroundedAnswer:
    """Ask a web-grounded question and return the answer with its sources.

    Args:
        query: The natural-language question (the Agent API ``input``).
        model: A specific model id (for example ``"openai/gpt-5.6-sol"``).
            Mutually exclusive with ``preset``.
        preset: A preset name (for example ``"low"`` or ``"medium"``) that
            bundles model, tools, and limits. Mutually exclusive with ``model``.
            When neither is given, :data:`DEFAULT_PRESET` is used.
        enable_web_search: When ``tools`` is not given, add the ``web_search``
            tool so the answer is grounded. Set ``False`` to leave tool
            selection entirely to the preset.
        tools: Explicit tool specs, overriding ``enable_web_search``.
        response_format: A JSON-schema ``response_format`` for structured output.
        previous_response_id: Continue a prior turn by id (multi-turn).
        instructions: Optional system-style instructions.
        max_output_tokens: Optional output-length cap.
        client: An existing SDK client; one is built from the environment key
            when omitted.

    Returns:
        A :class:`GroundedAnswer`.

    Raises:
        ExecutionFailure: On an empty query, conflicting ``model``/``preset``, a
            missing key, or any Perplexity API error (mapped to a canonical
            failure kind and status code).
        ImportError: When the optional ``perplexityai`` package is not installed
            and no ``client`` was supplied.
    """
    if not query.strip():
        raise ExecutionFailure(
            kind=FailureKind.INVALID_REQUEST,
            status_code=400,
            message="query must not be empty",
            retryable=False,
        )
    if model is not None and preset is not None:
        raise ExecutionFailure(
            kind=FailureKind.INVALID_REQUEST,
            status_code=400,
            message="pass either model or preset, not both",
            retryable=False,
        )

    resolved_tools = _resolve_tools(tools, enable_web_search=enable_web_search)
    request: dict[str, Any] = {"input": query}
    if model is not None:
        request["model"] = model
    elif preset is not None:
        request["preset"] = preset
    else:
        request["preset"] = DEFAULT_PRESET
    if resolved_tools:
        request["tools"] = resolved_tools
    if response_format is not None:
        request["response_format"] = response_format
    if previous_response_id is not None:
        request["previous_response_id"] = previous_response_id
    if instructions is not None:
        request["instructions"] = instructions
    if max_output_tokens is not None:
        request["max_output_tokens"] = max_output_tokens

    active_client = client if client is not None else build_client()

    logger.info(
        "PERPLEXITY_AGENT_REQUEST selector={} tools={} continues={} query_chars={}",
        request.get("model") or f"preset:{request.get('preset')}",
        [tool.get("type") for tool in resolved_tools],
        previous_response_id is not None,
        len(query),
    )

    try:
        result = active_client.responses.create(**request)
    except Exception as exc:
        raise _map_error(exc) from exc

    if not hasattr(result, "output"):
        raise ExecutionFailure(
            kind=FailureKind.UPSTREAM,
            status_code=502,
            message="unexpected streaming response for a non-streaming request",
            retryable=False,
        )

    answer = _parse_response(result)
    logger.info(
        "PERPLEXITY_AGENT_RESPONSE id={} status={} answer_chars={} sources={} citations={}",
        answer.response_id,
        answer.status,
        len(answer.text),
        len(answer.sources),
        len(answer.citations),
    )
    return answer


def _resolve_tools(
    tools: Sequence[Mapping[str, object]] | None,
    *,
    enable_web_search: bool,
) -> list[dict[str, object]]:
    if tools is not None:
        return [dict(tool) for tool in tools]
    if enable_web_search:
        return [dict(WEB_SEARCH_TOOL)]
    return []


def _parse_response(response: Any) -> GroundedAnswer:
    """Extract answer text, sources, and citations from an Agent response.

    Duck-typed on purpose: it reads the documented fields by attribute rather
    than importing the optional SDK's models, so it needs no ``perplexity``
    import and tolerates output-item variants it does not recognize.
    """
    citations: list[Citation] = []
    sources: list[SearchSource] = []
    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None)
        if item_type == "message":
            citations.extend(
                Citation(
                    url=getattr(annotation, "url", None),
                    title=getattr(annotation, "title", None),
                    start_index=getattr(annotation, "start_index", None),
                    end_index=getattr(annotation, "end_index", None),
                )
                for content in getattr(item, "content", None) or []
                for annotation in getattr(content, "annotations", None) or []
            )
        elif item_type == "search_results":
            sources.extend(
                SearchSource(
                    url=getattr(result, "url", None),
                    title=getattr(result, "title", None),
                    snippet=getattr(result, "snippet", None),
                    date=getattr(result, "date", None),
                    last_updated=getattr(result, "last_updated", None),
                    source=getattr(result, "source", None),
                )
                for result in getattr(item, "results", None) or []
            )

    usage_model = getattr(response, "usage", None)
    usage = usage_model.model_dump() if usage_model is not None else None
    return GroundedAnswer(
        text=getattr(response, "output_text", "") or "",
        response_id=getattr(response, "id", "") or "",
        status=getattr(response, "status", "") or "",
        model=getattr(response, "model", "") or "",
        citations=tuple(citations),
        sources=tuple(sources),
        usage=usage,
    )


def _retry_after_seconds(exc: object) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except TypeError, ValueError:
        return None


def _map_error(exc: Exception) -> ExecutionFailure:
    """Map a Perplexity SDK exception onto a canonical execution failure."""
    import perplexity

    if isinstance(exc, ExecutionFailure):
        return exc

    if isinstance(exc, perplexity.APITimeoutError):
        return ExecutionFailure(
            kind=FailureKind.TIMEOUT,
            status_code=408,
            message="Perplexity request timed out.",
            retryable=True,
        )
    if isinstance(exc, perplexity.APIConnectionError):
        return ExecutionFailure(
            kind=FailureKind.UNAVAILABLE,
            status_code=503,
            message="Could not reach the Perplexity API.",
            retryable=True,
        )
    if isinstance(exc, perplexity.AuthenticationError):
        return ExecutionFailure(
            kind=FailureKind.AUTHENTICATION,
            status_code=401,
            message=(
                "Perplexity rejected the credentials (401). Check "
                f"{PERPLEXITY_API_KEY_ENV}; rotate the key in the console if it "
                "may be exposed."
            ),
            retryable=False,
        )
    if isinstance(exc, perplexity.PermissionDeniedError):
        return ExecutionFailure(
            kind=FailureKind.PERMISSION,
            status_code=403,
            message="Perplexity denied access to this model or preset (403).",
            retryable=False,
        )
    if isinstance(exc, perplexity.RateLimitError):
        retry_after = _retry_after_seconds(exc)
        hint = f" Retry after {retry_after:g}s." if retry_after is not None else ""
        return ExecutionFailure(
            kind=FailureKind.RATE_LIMIT,
            status_code=429,
            message=f"Perplexity rate limit hit (429, retries exhausted).{hint}",
            retryable=True,
        )
    if isinstance(exc, perplexity.InternalServerError):
        status = getattr(exc, "status_code", 502) or 502
        return ExecutionFailure(
            kind=FailureKind.OVERLOADED,
            status_code=status,
            message=f"Perplexity is temporarily unavailable ({status}).",
            retryable=True,
        )
    if isinstance(exc, perplexity.APIStatusError):
        status = getattr(exc, "status_code", 502) or 502
        return ExecutionFailure(
            kind=FailureKind.UPSTREAM,
            status_code=status,
            message=f"Perplexity API error ({status}).",
            retryable=status >= 500,
        )

    return ExecutionFailure(
        kind=FailureKind.UPSTREAM,
        status_code=502,
        message="Unexpected Perplexity client error.",
        retryable=False,
    )
