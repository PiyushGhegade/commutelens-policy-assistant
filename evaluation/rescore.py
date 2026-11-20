"""Score saved response JSONL using current gold rubrics, with zero provider calls."""

import argparse
import json
from pathlib import Path

from app.auth import USERS
from evaluation.scoring import RUBRIC_VERSION, fact_checks, score

ROOT = Path(__file__).resolve().parents[1]


def rescore(input_path, output_path):
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Use a different output path to preserve the original responses")
    gold = {
        row["id"]: row
        for line in (ROOT / "evaluation/questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
    }
    results = []
    for line in input_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        saved = json.loads(line)
        case = gold[saved["id"]]
        if saved["input"] != case["input"]:
            raise ValueError("Saved input differs from fixed gold input")
        actual = dict(saved["actual"])
        company = USERS[case["input"]["username"]][0]
        policy = json.loads((ROOT / "policies" / f"{company}.json").read_text(encoding="utf-8"))
        passed, checks = score(case, actual, policy)
        actual["checks"] = checks
        actual["fact_checks"] = fact_checks(case["expected"], actual["answer"])
        results.append(
            {
                **case,
                "actual": actual,
                "pass": passed,
                "notes": case["notes"]
                + " Rescored saved response offline; no new model response or latency measurement.",
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results), encoding="utf-8"
    )
    return {
        "rubric_version": RUBRIC_VERSION,
        "mode": "saved_responses_no_api",
        "cases": len(results),
        "passed": sum(row["pass"] for row in results),
        "missing_verdicts": sum(row["actual"].get("verdict") is None for row in results),
        "failed_ids": [row["id"] for row in results if not row["pass"]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = rescore(args.input, args.output)
    print(json.dumps(result, indent=2))
    return int(args.strict and result["passed"] != result["cases"])


if __name__ == "__main__":
    raise SystemExit(main())
