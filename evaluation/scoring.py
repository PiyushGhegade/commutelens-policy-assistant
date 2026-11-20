"""Versioned, deterministic rubric checks. This is not a semantic grading model."""

import re
import unicodedata

from app.auth import USERS

RUBRIC_VERSION = 2
WORDS = dict(zip("zero one two three four five six seven eight nine ten".split(), map(str, range(11))))


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("₹", " inr ").replace("’", "'")
    # Permit 1,500 / 1500, seven-day / 7 days, 8 p.m. / 8 PM, etc.
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = re.sub(r"\b([ap])\s*\.\s*m\.?", r"\1m", text)
    text = re.sub(r"\b(" + "|".join(WORDS) + r")\b", lambda m: WORDS[m[0]], text)
    text = re.sub(r"[-–—]", " ", text)
    return " ".join(text.split())


def fact_checks(expected, answer):
    text = normalize(answer)
    return {
        fact["id"]: any(re.search(pattern, text) for pattern in fact["any_of"]) for fact in expected["facts"]
    }


def score(case, actual, policy):
    expected = case["expected"]
    if not expected.get("verdicts") or "facts" not in expected:
        raise ValueError("Missing version-2 gold verdict/fact rubric")
    citations = actual.get("citations", [])
    got = {c["section_id"] for c in citations}
    source = {s["id"]: s for s in policy["sections"]}
    valid = all(
        c["section_id"] in source
        and c["quote"] == source[c["section_id"]]["text"]
        and c["section"] == source[c["section_id"]]["title"]
        and c["document"] == policy["document"]
        and c["version"] == policy["version"]
        for c in citations
    )
    checks = {
        "status": actual["status"] == expected["status"],
        "verdict": actual.get("verdict") in expected["verdicts"],
        "sections": got == set(expected["sections"]),
        "facts": all(fact_checks(expected, actual["answer"]).values()),
        "no_known_contradiction": not any(
            re.search(pattern, normalize(actual["answer"])) for pattern in expected.get("forbidden", [])
        ),
        "citations_valid": valid,
        "scope": actual["company"] == USERS[case["input"]["username"]][0],
        "budgets": 0 <= actual["llm_calls"] <= 2 and len(citations) <= 3,
        "direct_answer": actual["status"] != "answered"
        or (
            actual.get("answer_style") == "direct"
            and all(normalize(c["quote"]) not in normalize(actual["answer"]) for c in citations)
        ),
    }
    return all(checks.values()), checks
