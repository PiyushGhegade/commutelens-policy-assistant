"""Scoring regressions using the fixed questions and hand-written sample outputs.

These fixtures test the evaluator, not the real model's accuracy.
"""

import copy
import json
from pathlib import Path

import pytest

from app.auth import USERS
from evaluation.rescore import rescore
from evaluation.scoring import fact_checks, score

ROOT = Path(__file__).resolve().parents[1]
GOLD = {
    r["id"]: r
    for line in (ROOT / "evaluation/questions.jsonl").read_text(encoding="utf-8").splitlines()
    for r in [json.loads(line)]
}
ANSWERS = {
    "atlas-night": "For female employees, a security escort is required after 8 p.m.",
    "beacon-night": "Women need a security escort for drops later than 22:00.",
    "cedar-night": "After nine PM, all genders require a security escort.",
    "atlas-saturday": "It depends. For Saturday pickups, get permission from your line manager beforehand.",
    "beacon-saturday": "It depends. Saturday pickups are available for scheduled shifts; manager approval is not needed.",
    "cedar-sunday": "It depends. Sunday and public holiday pickups are available for rostered night shifts, without additional manager approval.",
    "atlas-airport": "Get approval from the department head. The limit is Rs. 1,500 per trip.",
    "beacon-airport": "The finance manager must approve the airport trip. The maximum is INR 2,500 per ride.",
    "cedar-airport": "No. Airport cab trips are not available through this policy.",
    "atlas-noshow": "Your booking access is suspended for one week.",
    "beacon-noshow": "You receive a warning in writing.",
    "cedar-noshow": "The penalty is INR 100 per no-show. Two no-shows do not suspend access.",
    "atlas-cutoff": "Send the request at least two hours before departure.",
    "beacon-cutoff": "Request the change a minimum of four hrs before the trip.",
    "cedar-eligibility": "No. Day-shift employees are ineligible for regular cab transport.",
    "beacon-guest": "It depends. You need permission from the site administrator.",
    "paraphrase-night": "A security escort is required for your stated drop scenario.",
    "paraphrase-noshow": "You receive a written notice.",
    "compound-covered": "The airport cap is INR 1,500 per trip. Two missed rides result in booking access being blocked for seven days.",
    "exact-boundary": "No. At 20:00, an escort is not mandatory under this rule.",
}


def sample(case_id):
    case = GOLD[case_id]
    expected = case["expected"]
    company = USERS[case["input"]["username"]][0]
    policy = json.loads((ROOT / "policies" / f"{company}.json").read_text(encoding="utf-8"))
    sections = {s["id"]: s for s in policy["sections"]}
    actual = {
        "status": expected["status"],
        "verdict": expected["verdicts"][0],
        "answer": ANSWERS.get(case_id, "I could not find this in the policy. Contact the transport desk."),
        "company": company,
        "version": policy["version"],
        "llm_calls": 1,
        "answer_style": "direct",
        "citations": [
            {
                "section_id": sid,
                "section": sections[sid]["title"],
                "quote": sections[sid]["text"],
                "document": policy["document"],
                "version": policy["version"],
            }
            for sid in expected["sections"]
        ],
    }
    return case, actual, policy


@pytest.mark.parametrize("case_id", list(GOLD))
def test_fixed_rubric_accepts_reviewed_wording_and_rejects_wrong_verdict(case_id):
    case, actual, policy = sample(case_id)
    passed, checks = score(case, actual, policy)
    assert passed, (case_id, checks, fact_checks(case["expected"], actual["answer"]))
    # Correct sections, facts, and quotes cannot rescue a wrong conclusion.
    wrong = next(
        v
        for v in ["yes", "no", "conditional", "information", "not_covered"]
        if v not in case["expected"]["verdicts"]
    )
    actual["verdict"] = wrong
    passed, checks = score(case, actual, policy)
    assert not passed and not checks["verdict"]
    assert checks["facts"] and checks["citations_valid"] and checks["sections"]


@pytest.mark.parametrize(
    "body",
    [
        "Yes. Saturday pickups are available.",
        "Yes. Saturday pickups require prior approval.",
        "Yes. Get line manager approval for Saturday pickups.",
    ],
)
def test_saturday_answer_must_retain_approver_and_prior_condition(body):
    case, actual, policy = sample("atlas-saturday")
    actual.update(verdict="yes", answer=body)
    assert not score(case, actual, policy)[0]


@pytest.mark.parametrize(
    "case_id,body",
    [
        ("atlas-saturday", "Yes. Saturday pickups are available without prior line manager approval."),
        ("cedar-airport", "No. Airport trips are not offered, but you can book an airport cab."),
        ("beacon-noshow", "No written warning is issued."),
        (
            "exact-boundary",
            "No. An escort is not required generally, but an escort is mandatory at exactly 8 PM.",
        ),
    ],
)
def test_known_contradiction_cannot_pass_by_mentioning_right_keywords(case_id, body):
    case, actual, policy = sample(case_id)
    actual["answer"] = body
    passed, checks = score(case, actual, policy)
    assert not passed and not checks["no_known_contradiction"]


def test_old_phrase_need_not_appear_when_equivalent_wording_is_accepted():
    case, actual, policy = sample("atlas-noshow")
    assert "7-day suspension" not in actual["answer"]
    assert score(case, actual, policy)[0]


def test_missing_verdict_is_not_guessed_from_legacy_prose():
    case, actual, policy = sample("cedar-airport")
    del actual["verdict"]
    passed, checks = score(case, actual, policy)
    assert not passed and not checks["verdict"]


@pytest.mark.parametrize(
    "field,value,failed_check",
    [
        ("company", "beacon", "scope"),
        ("llm_calls", 3, "budgets"),
        ("answer_style", "policy_excerpt", "direct_answer"),
    ],
)
def test_strengthened_scoring_preserves_existing_guards(field, value, failed_check):
    case, actual, policy = sample("atlas-airport")
    actual[field] = value
    assert not score(case, actual, policy)[1][failed_check]


def test_invented_quote_is_rejected():
    case, actual, policy = sample("atlas-airport")
    actual["citations"][0]["quote"] = "A made-up policy quote."
    assert not score(case, actual, policy)[1]["citations_valid"]


def test_rescoring_uses_current_gold_without_mutating_original(tmp_path):
    case, actual, _ = sample("atlas-airport")
    saved = {**copy.deepcopy(case), "actual": actual, "pass": False}
    original = json.dumps(saved)
    path = tmp_path / "saved.jsonl"
    output = tmp_path / "rescored.jsonl"
    path.write_text(original + "\n", encoding="utf-8")
    result = rescore(path, output)
    assert result["passed"] == 1 and result["mode"] == "saved_responses_no_api"
    assert path.read_text(encoding="utf-8") == original + "\n"
    assert json.loads(output.read_text(encoding="utf-8"))["actual"]["checks"]["verdict"]
    with pytest.raises(ValueError, match="different output"):
        rescore(path, path)
