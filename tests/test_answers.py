"""Original reported examples with injected outputs. No network or Gemini quota."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.models import AnswerPoint, Policy, PolicyResponse
from app.retrieval import Hit
from tests.conftest import auth
from tests.test_recovery import OutcomeLLM

ROOT = Path(__file__).resolve().parents[1]


def sections():
    policy = Policy.model_validate_json((ROOT / "policies/atlas.json").read_text())
    return {s.id: s for s in policy.sections}


@pytest.mark.parametrize(
    "question,verdict,points,expected",
    [
        (
            "My airport cab costs INR 1,800, and my department head has approved it. Is the full amount within the allowed limit?",
            "no",
            [
                {
                    "text": "Your INR 1,800 fare exceeds the INR 1,500 per-trip cap by INR 300. Department-head approval meets the approval requirement but does not change the cap.",
                    "section_ids": ["airport"],
                }
            ],
            "No. Your INR 1,800 fare exceeds",
        ),
        (
            "Can I book a cab for Saturday, and how many hours before the trip must I request it?",
            "conditional",
            [
                {
                    "text": "You can book a Saturday pickup with prior line manager approval.",
                    "section_ids": ["weekend"],
                },
                {"text": "Request it at least 2 hours before the scheduled trip.", "section_ids": ["cutoff"]},
            ],
            "It depends. You can book a Saturday pickup",
        ),
        (
            "If my cab drops me at 9:30 PM, will I get a security escort?",
            "conditional",
            [
                {
                    "text": "If you are a woman employee, your 9:30 PM drop falls after the 8 PM threshold and requires an escort. The supplied rule does not establish the requirement for other employees.",
                    "section_ids": ["night"],
                }
            ],
            "It depends. If you are a woman employee",
        ),
    ],
)
def test_reported_examples_render_reasoning_separately_from_sources(
    settings, store, monkeypatch, question, verdict, points, expected
):
    source = sections()
    draft = PolicyResponse(verdict=verdict, points=points)
    monkeypatch.setattr(
        "app.main.retrieve", lambda *args: [Hit(source[sid], 1) for sid in reversed(draft.section_ids)]
    )
    llm = OutcomeLLM(draft)
    # Test injected prose presentation, not remote model reasoning quality.
    settings.llm_provider = "gemini"
    with TestClient(create_app(settings, store=store, llm=llm)) as client:
        data = client.post("/questions", json={"question": question}, headers=auth(client)).json()
    assert data["status"] == "answered" and data["verdict"] == verdict
    assert data["answer"].startswith(expected) and data["llm_calls"] == 1
    assert data["answer_style"] == "direct"
    assert [c["section_id"] for c in data["citations"]] == draft.section_ids
    for index, citation in enumerate(data["citations"], 1):
        assert citation["quote"] == source[citation["section_id"]].text
        assert citation["quote"] not in data["answer"]
        assert f"[{index}]" in data["answer"]


@pytest.mark.parametrize(
    "draft",
    [
        {"verdict": "yes", "points": []},
        {"verdict": "not_covered", "points": [{"text": "Not allowed.", "section_ids": ["airport"]}]},
        {"verdict": "no", "points": [{"text": "No citation.", "section_ids": []}]},
        {"verdict": "no", "points": [{"text": "Invented citation [9].", "section_ids": ["airport"]}]},
        {"verdict": "no", "points": [{"text": "Duplicate citation.", "section_ids": ["airport", "airport"]}]},
        {
            "verdict": "no",
            "points": [
                {"text": "Too many references.", "section_ids": ["airport", "cutoff", "night"]},
                {"text": "Another.", "section_ids": ["weekend"]},
            ],
        },
    ],
)
def test_invalid_verdict_and_evidence_contract_is_rejected(draft):
    with pytest.raises(ValidationError):
        PolicyResponse.model_validate(draft)


def test_invented_evidence_id_cannot_be_published(settings, store, monkeypatch):
    monkeypatch.setattr("app.main.retrieve", lambda *args: [Hit(sections()["airport"], 1)])
    llm = OutcomeLLM(
        PolicyResponse(verdict="no", points=[AnswerPoint(text="A claim.", section_ids=["invented"])])
    )
    with TestClient(create_app(settings, store=store, llm=llm)) as client:
        data = client.post(
            "/questions",
            json={"question": "Is the full airport fare within the allowed limit?"},
            headers=auth(client),
        ).json()
    assert data["status"] == "try_again" and not data["citations"]
    assert "A claim" not in data["answer"]
