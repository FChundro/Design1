"""Deterministic unit tests for the Perplexity Agent integration.

No network and no API key are required: response models are built locally with
``model_construct`` and the SDK client is replaced by monkeypatching
``build_client``.
"""

from typing import Any

import perplexity
import pytest
from perplexity.types.annotation import Annotation
from perplexity.types.content_part import ContentPart
from perplexity.types.output_item import MessageOutputItem, SearchResultsOutputItem
from perplexity.types.response_create_response import ResponseCreateResponse
from perplexity.types.shared.search_result import SearchResult

from free_claude_code.core.failures import ExecutionFailure, FailureKind
from free_claude_code.integrations import perplexity_agent
from free_claude_code.integrations.perplexity_agent import (
    Citation,
    SearchSource,
    api_key_present,
    build_client,
    web_grounded_answer,
)


class _FakeResponses:
    def __init__(self, result: object, recorder: dict[str, Any]) -> None:
        self._result = result
        self._recorder = recorder

    def create(self, **kwargs: Any) -> object:
        self._recorder.update(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeClient:
    def __init__(self, result: object) -> None:
        self.recorded: dict[str, Any] = {}
        self.responses = _FakeResponses(result, self.recorded)


def _sample_response() -> ResponseCreateResponse:
    message = MessageOutputItem.model_construct(
        id="msg_1",
        role="assistant",
        status="completed",
        type="message",
        content=[
            ContentPart.model_construct(
                text="MCP is an open protocol.",
                type="output_text",
                annotations=[
                    Annotation.model_construct(
                        url="https://modelcontextprotocol.io",
                        title="MCP",
                        start_index=0,
                        end_index=3,
                    )
                ],
            )
        ],
    )
    search = SearchResultsOutputItem.model_construct(
        type="search_results",
        queries=["what is mcp"],
        results=[
            SearchResult.model_construct(
                id="src_1",
                snippet="An open protocol.",
                title="Model Context Protocol",
                url="https://modelcontextprotocol.io",
                date=None,
                last_updated=None,
                source="web",
            )
        ],
    )
    return ResponseCreateResponse.model_construct(
        id="resp_1",
        created_at=0,
        model="test-model",
        object="response",
        status="completed",
        output=[message, search],
        usage=None,
        previous_response_id=None,
    )


def _install_fake(monkeypatch: pytest.MonkeyPatch, result: object) -> _FakeClient:
    fake = _FakeClient(result)
    monkeypatch.setattr(perplexity_agent, "build_client", lambda: fake)
    return fake


def test_api_key_present_checks_env_without_exposing_value() -> None:
    assert api_key_present({"PERPLEXITY_API_KEY": "pplx-secret"}) is True
    assert api_key_present({"PERPLEXITY_API_KEY": "  "}) is False
    assert api_key_present({}) is False


def test_web_grounded_answer_parses_text_sources_and_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_fake(monkeypatch, _sample_response())

    answer = web_grounded_answer("what is mcp")

    assert answer.text == "MCP is an open protocol."
    assert answer.response_id == "resp_1"
    assert answer.status == "completed"
    assert answer.sources == (
        SearchSource(
            url="https://modelcontextprotocol.io",
            title="Model Context Protocol",
            snippet="An open protocol.",
            date=None,
            last_updated=None,
            source="web",
        ),
    )
    assert answer.citations == (
        Citation(
            url="https://modelcontextprotocol.io",
            title="MCP",
            start_index=0,
            end_index=3,
        ),
    )
    # Default request: balanced preset plus web grounding.
    assert fake.recorded["input"] == "what is mcp"
    assert fake.recorded["preset"] == "medium"
    assert fake.recorded["tools"] == [{"type": "web_search"}]
    assert "model" not in fake.recorded


def test_web_grounded_answer_uses_model_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_fake(monkeypatch, _sample_response())

    web_grounded_answer(
        "hi",
        model="openai/gpt-5.6-sol",
        previous_response_id="resp_0",
        max_output_tokens=256,
    )

    assert fake.recorded["model"] == "openai/gpt-5.6-sol"
    assert "preset" not in fake.recorded
    assert fake.recorded["previous_response_id"] == "resp_0"
    assert fake.recorded["max_output_tokens"] == 256


def test_web_grounded_answer_disables_tools_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_fake(monkeypatch, _sample_response())

    web_grounded_answer("hi", enable_web_search=False)

    assert "tools" not in fake.recorded


def test_web_grounded_answer_forwards_explicit_tools_and_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_fake(monkeypatch, _sample_response())
    schema = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}

    web_grounded_answer(
        "hi",
        tools=[{"type": "fetch_url"}],
        response_format=schema,
    )

    assert fake.recorded["tools"] == [{"type": "fetch_url"}]
    assert fake.recorded["response_format"] == schema


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ExecutionFailure) as excinfo:
        web_grounded_answer("   ")
    assert excinfo.value.kind is FailureKind.INVALID_REQUEST
    assert excinfo.value.status_code == 400


def test_model_and_preset_conflict_is_rejected() -> None:
    with pytest.raises(ExecutionFailure) as excinfo:
        web_grounded_answer("hi", model="m", preset="medium")
    assert excinfo.value.kind is FailureKind.INVALID_REQUEST


def test_build_client_without_key_raises_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    with pytest.raises(ExecutionFailure) as excinfo:
        build_client()
    assert excinfo.value.kind is FailureKind.AUTHENTICATION
    assert excinfo.value.status_code == 401
    # The guidance must not leak a key value.
    assert "pplx-" not in excinfo.value.message


def test_api_error_is_mapped_to_execution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limit = perplexity.RateLimitError.__new__(perplexity.RateLimitError)
    _install_fake(monkeypatch, rate_limit)

    with pytest.raises(ExecutionFailure) as excinfo:
        web_grounded_answer("hi")

    assert excinfo.value.kind is FailureKind.RATE_LIMIT
    assert excinfo.value.status_code == 429
    assert excinfo.value.retryable is True


@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (perplexity.APITimeoutError, FailureKind.TIMEOUT, True),
        (perplexity.AuthenticationError, FailureKind.AUTHENTICATION, False),
        (perplexity.PermissionDeniedError, FailureKind.PERMISSION, False),
        (perplexity.InternalServerError, FailureKind.OVERLOADED, True),
    ],
)
def test_map_error_matrix(
    exc: type[Exception], kind: FailureKind, retryable: bool
) -> None:
    instance = exc.__new__(exc)
    failure = perplexity_agent._map_error(instance)
    assert failure.kind is kind
    assert failure.retryable is retryable
