import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm import FakeLLM, GeminiLLM, ProviderError
from app.main import create_app
from app.models import AnswerPoint, PolicyResponse
from tests.conftest import auth


class OutcomeLLM(FakeLLM):
    def __init__(self, outcome, name="test-primary", delay=0):
        self.outcome, self.model_name, self.delay, self.calls = outcome, name, delay, 0

    async def respond(self, question, hits):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.mark.parametrize("reason", ["llm_unavailable", "network_error", "llm_timeout", "model_unavailable"])
def test_one_fallback_recovers_inside_same_request(settings, store, reason):
    first = OutcomeLLM(ProviderError(reason, http_status=503))
    second = OutcomeLLM(
        PolicyResponse(
            verdict="conditional",
            points=[
                AnswerPoint(
                    text="For women employees, drops after 8 PM require a security escort.",
                    section_ids=["night"],
                )
            ],
        ),
        "test-fallback",
    )
    with TestClient(create_app(settings, store=store, llm=first, fallback_llm=second)) as client:
        response = client.post(
            "/questions",
            json={"question": "If my cab drops me at 9:30 PM, will I get a security escort?"},
            headers=auth(client),
        )
        result = response.json()
        assert result["status"] == "answered"
        assert "For women employees" in result["answer"] and "8 PM" in result["answer"]
        assert result["llm_calls"] == 2 and first.calls == second.calls == 1
        assert result["llm_model"] == "test-fallback"
        assert [a["status"] for a in result["llm_attempts"]] == [reason, "ok"]
        assert result["llm_attempts"][0]["http_status"] == 503
        assert result["citations"][0]["version"] == 1


@pytest.mark.parametrize("reason", ["quota", "auth_error", "invalid_request", "invalid_output"])
def test_configuration_quota_and_invalid_output_are_not_retried(settings, store, reason):
    first = OutcomeLLM(ProviderError(reason))
    second = OutcomeLLM(
        PolicyResponse(
            verdict="conditional",
            points=[
                AnswerPoint(
                    text="For women employees, drops after 8 PM require a security escort.",
                    section_ids=["night"],
                )
            ],
        )
    )
    with TestClient(create_app(settings, store=store, llm=first, fallback_llm=second)) as client:
        result = client.post(
            "/questions", json={"question": "When is an escort required?"}, headers=auth(client)
        ).json()
        assert result["status"] == "try_again" and result["reason"] == reason
        assert result["llm_calls"] == 1 and second.calls == 0
        assert not result["citations"] and result["request_id"]


def test_two_slow_calls_cannot_extend_total_deadline(settings, store):
    settings.answer_timeout = 0.2
    settings.first_llm_timeout = 0.06
    first = OutcomeLLM(
        PolicyResponse(
            verdict="conditional",
            points=[
                AnswerPoint(
                    text="For women employees, drops after 8 PM require a security escort.",
                    section_ids=["night"],
                )
            ],
        ),
        delay=0.4,
    )
    second = OutcomeLLM(
        PolicyResponse(
            verdict="conditional",
            points=[
                AnswerPoint(
                    text="For women employees, drops after 8 PM require a security escort.",
                    section_ids=["night"],
                )
            ],
        ),
        delay=0.4,
    )
    with TestClient(create_app(settings, store=store, llm=first, fallback_llm=second)) as client:
        result = client.post(
            "/questions", json={"question": "When is an escort required?"}, headers=auth(client)
        ).json()
        assert result["status"] == "try_again"
        assert result["latency_ms"] < 250
        assert result["llm_calls"] == 2 and len(result["llm_attempts"]) == 2


def test_failure_metadata_never_logs_key_or_question(settings, store, caplog):
    first = OutcomeLLM(ProviderError("auth_error", http_status=403))
    with TestClient(create_app(settings, store=store, llm=first)) as client:
        result = client.post(
            "/questions", json={"question": "private-question-phrase about an escort"}, headers=auth(client)
        ).json()
        assert result["request_id"] in caplog.text
        assert "403" in caplog.text and "auth_error" in caplog.text
        assert "private-question-phrase" not in caplog.text
        if settings.gemini_api_key:
            assert settings.gemini_api_key not in caplog.text


@pytest.mark.parametrize(
    "status, expected",
    [
        (400, "invalid_request"),
        (401, "auth_error"),
        (403, "auth_error"),
        (404, "model_unavailable"),
        (429, "quota"),
        (503, "llm_unavailable"),
    ],
)
def test_http_failures_preserve_safe_status_metadata(status, expected):
    with pytest.raises(ProviderError, match=expected) as exc:
        GeminiLLM.check_response(httpx.Response(status))
    assert exc.value.http_status == status
