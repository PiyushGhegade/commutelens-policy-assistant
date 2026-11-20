import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.llm import FakeLLM, ProviderError
from app.main import create_app
from app.models import AnswerPoint, PolicyResponse
from tests.conftest import auth


class StubLLM(FakeLLM):
    def __init__(self, result):
        self.result = result

    async def respond(self, question, hits):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize(
    "result",
    [
        {"section_ids": ["not-in-retrieved-evidence"], "not_covered": False},
        {"section_ids": ["night"] * 4, "not_covered": False},
        {"section_ids": ["night"], "not_covered": True},
        {"section_ids": ["night"], "not_covered": False, "answer": "invented"},
        "not JSON",
        RuntimeError("SECRET internal database error"),
    ],
)
def test_untrusted_model_output_fails_closed(settings, store, result):
    with TestClient(create_app(settings, store=store, llm=StubLLM(result))) as c:
        data = c.post("/questions", json={"question": "When is an escort required?"}, headers=auth(c)).json()
        assert data["status"] == "try_again"
        assert data["citations"] == []
        assert "SECRET" not in str(data) and "invented" not in str(data)
        assert data["llm_calls"] == 1


@pytest.mark.parametrize("error", ["quota", "llm_unavailable", "missing_key", "invalid_output"])
def test_provider_errors_are_actionable(settings, store, error):
    with TestClient(create_app(settings, store=store, llm=StubLLM(ProviderError(error)))) as c:
        data = c.post("/questions", json={"question": "When is an escort required?"}, headers=auth(c)).json()
        assert data["status"] == "try_again"
        assert "transport desk" in data["answer"]
        assert data["reason"] == error


def test_no_evidence_says_not_covered(settings, store):
    with TestClient(
        create_app(settings, store=store, llm=StubLLM(PolicyResponse(verdict="not_covered", points=[])))
    ) as c:
        data = c.post(
            "/questions", json={"question": "Does the policy cover bicycle repairs?"}, headers=auth(c)
        ).json()
        assert data["status"] == "not_covered"
        assert not data["citations"] and "transport desk" in data["answer"]


def test_llm_deadline_returns_instead_of_hanging(settings, store):
    class Slow(FakeLLM):
        async def respond(self, question, hits):
            await asyncio.sleep(0.3)
            return PolicyResponse(
                verdict="conditional",
                points=[
                    AnswerPoint(
                        text="For women employees, drops after 8 PM require a security escort.",
                        section_ids=["night"],
                    )
                ],
            )

    settings.answer_timeout = 0.08
    with TestClient(create_app(settings, store=store, llm=Slow())) as c:
        started = time.perf_counter()
        data = c.post("/questions", json={"question": "When is an escort required?"}, headers=auth(c)).json()
        assert time.perf_counter() - started < 0.25
        assert data["status"] == "try_again" and data["reason"] == "llm_timeout"


def test_retrieval_timeout_is_distinct(settings, store, monkeypatch):
    import app.main

    original = app.main.retrieve

    def slow(*args):
        time.sleep(0.15)
        return original(*args)

    monkeypatch.setattr(app.main, "retrieve", slow)
    settings.retrieval_timeout = 0.02
    with TestClient(create_app(settings, store=store, llm=FakeLLM())) as c:
        data = c.post("/questions", json={"question": "When is an escort required?"}, headers=auth(c)).json()
        assert data["status"] == "try_again" and data["reason"] == "retrieval_timeout"
        assert data["llm_calls"] == 0


def test_retrieval_scope_corruption_never_reaches_llm(settings, store, monkeypatch):
    from chromadb.api.models.Collection import Collection

    original = Collection.query

    def poisoned(self, **kwargs):
        data = original(self, **kwargs)
        data["metadatas"][0][0]["company"] = "beacon"
        return data

    monkeypatch.setattr(Collection, "query", poisoned)
    with TestClient(create_app(settings, store=store, llm=FakeLLM())) as c:
        data = c.post("/questions", json={"question": "When is an escort required?"}, headers=auth(c)).json()
        assert data["status"] == "try_again" and data["llm_calls"] == 0
        assert data["citations"] == []


def test_citations_are_exact_current_source_text(client, store):
    data = client.post(
        "/questions", json={"question": "What is the airport trip cost cap?"}, headers=auth(client)
    ).json()
    assert data["status"] == "answered" and data["llm_calls"] <= 2
    policy = store.active("atlas").policy
    assert 1 <= len(data["citations"]) <= 3
    for citation in data["citations"]:
        section = next(s for s in policy.sections if s.id == citation["section_id"])
        assert citation["quote"] == section.text
        assert citation["document"] == policy.document and citation["version"] == policy.version


def test_empty_question_is_a_plain_422(client):
    response = client.post("/questions", json={"question": ""}, headers=auth(client))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_empty_retrieval_never_calls_llm(client, monkeypatch):
    import app.main

    monkeypatch.setattr(app.main, "retrieve", lambda *args: [])
    data = client.post(
        "/questions", json={"question": "Are bicycle repairs reimbursed?"}, headers=auth(client)
    ).json()
    assert data["status"] == "not_covered" and data["llm_calls"] == 0
