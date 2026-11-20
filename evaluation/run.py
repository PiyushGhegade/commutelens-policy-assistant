"""Fixed gold set, API-level scoring, and measured dense/hybrid comparison.

python -m evaluation.run --provider fake --embedding hash-test
python -m evaluation.run --provider gemini --delay 7
"""

import argparse
import json
import math
import platform
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import ROOT, create_app
from evaluation.scoring import RUBRIC_VERSION, fact_checks, score


def percentile(values, p=95):
    return sorted(values)[max(0, math.ceil(p / 100 * len(values)) - 1)] if values else None


def evaluate(args):
    cases = [
        json.loads(line)
        for line in (ROOT / "evaluation/questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if args.limit:
        cases = cases[: args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    methods = ["dense", "hybrid"] if args.method == "both" else [args.method]
    summary = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "provider": args.provider,
        "rubric_version": RUBRIC_VERSION,
        "embedding": args.embedding,
        "timing": "Sequential local API calls; elapsed wall time includes LLM. First provider connection is included. Model/index warmup happens at app startup.",
        "answer_timeout_seconds": args.timeout,
        "sample_size_per_method": len(cases),
        "fake_notice": "Fake LLM measures pipeline behaviour only; it does not establish real LLM answer quality."
        if args.provider == "fake"
        else "Real remote LLM, no answer cache; one structured answer call by default inside the overall deadline.",
        "methods": {},
    }
    with tempfile.TemporaryDirectory(prefix="commute-eval-", ignore_cleanup_errors=True) as temporary:
        settings = Settings(
            data_dir=Path(temporary),
            llm_provider=args.provider,
            embedding_model=args.embedding,
            answer_timeout=args.timeout,
        )
        summary["model"] = "deterministic-overlap-test-double"
        if args.provider == "groq":
            summary["model"] = settings.groq_model
        elif args.provider == "gemini":
            summary["model"] = settings.gemini_model
        summary["response_mode"] = "grounded_generation"
        summary["automatic_retries"] = 0
        with TestClient(create_app(settings)) as client:
            headers = {}
            policies = {}
            for username in {case["input"]["username"] for case in cases}:
                result = client.post(
                    "/auth/demo-token", json={"username": username, "password": settings.demo_password}
                )
                result.raise_for_status()
                headers[username] = {"Authorization": "Bearer " + result.json()["access_token"]}
                policies[username] = client.get("/policy", headers=headers[username]).json()
            rows = {method: [] for method in methods}
            # Alternate method order to reduce systematic cold-connection/order bias.
            for index, case in enumerate(cases):
                order = methods if index % 2 == 0 else list(reversed(methods))
                for method in order:
                    if args.delay and args.provider != "fake":
                        time.sleep(args.delay)  # Pacing is outside the measured request.
                    started = time.perf_counter()
                    response = client.post(
                        "/questions",
                        json={"question": case["input"]["question"], "retrieval": method},
                        headers=headers[case["input"]["username"]],
                    )
                    elapsed = (time.perf_counter() - started) * 1000
                    response.raise_for_status()
                    actual = response.json()
                    actual["wall_ms"] = round(elapsed, 2)
                    passed, checks = score(case, actual, policies[case["input"]["username"]])
                    actual["checks"] = checks
                    actual["fact_checks"] = fact_checks(case["expected"], actual["answer"])
                    row = {
                        **case,
                        "actual": actual,
                        "pass": passed,
                        "notes": case["notes"] + f" Method={method}; provider={args.provider}.",
                    }
                    rows[method].append(row)
                    print(
                        f"{method:6} {case['id']:24} {'PASS' if passed else 'FAIL'} {elapsed:7.1f} ms {actual['status']} {actual['reason']}",
                        flush=True,
                    )
                    # Write continuously so an interrupted real-provider run remains reviewable.
                    with (args.output / f"{method}.jsonl").open(
                        "a" if len(rows[method]) > 1 else "w", encoding="utf-8"
                    ) as out:
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
            for method, results in rows.items():
                timings = [r["actual"]["wall_ms"] for r in results]
                gold = [r for r in results if r["expected"]["sections"]]
                recall = (
                    mean(
                        len(set(r["expected"]["sections"]) & set(r["actual"]["retrieved_ids"]))
                        / len(r["expected"]["sections"])
                        for r in gold
                    )
                    if gold
                    else None
                )
                mrr = (
                    mean(
                        next(
                            (
                                1 / (i + 1)
                                for i, sid in enumerate(r["actual"]["retrieved_ids"])
                                if sid in r["expected"]["sections"]
                            ),
                            0,
                        )
                        for r in gold
                    )
                    if gold
                    else None
                )
                negatives = [r for r in results if r["expected"]["status"] == "not_covered"]
                successful = [
                    r["actual"]["wall_ms"]
                    for r in results
                    if r["actual"]["status"] in {"answered", "not_covered"}
                ]
                cited = [r for r in results if r["actual"]["citations"]]
                summary["methods"][method] = {
                    "cases": len(results),
                    "passed": sum(r["pass"] for r in results),
                    "answer_accuracy": mean(r["pass"] for r in results),
                    "verdict_accuracy": mean(r["actual"]["checks"]["verdict"] for r in results),
                    "fact_accuracy": mean(r["actual"]["checks"]["facts"] for r in results),
                    "retrieval_recall_at_3": recall,
                    "retrieval_mrr_at_3": mrr,
                    "citation_validity": mean(r["actual"]["checks"]["citations_valid"] for r in cited)
                    if cited
                    else None,
                    "answers_with_citations": len(cited),
                    "direct_answer_rate": mean(r["actual"]["checks"]["direct_answer"] for r in cited)
                    if cited
                    else None,
                    "negative_accuracy": mean(r["pass"] for r in negatives) if negatives else None,
                    "p95_wall_ms": percentile(timings),
                    "p50_wall_ms": percentile(timings, 50),
                    "successful_reply_p95_ms": percentile(successful),
                    "mean_retrieval_ms": mean(r["actual"]["retrieval_ms"] for r in results),
                    "p95_retrieval_ms": percentile([r["actual"]["retrieval_ms"] for r in results]),
                    "try_again_count": sum(r["actual"]["status"] == "try_again" for r in results),
                    "reasons": dict(Counter(r["actual"]["reason"] for r in results)),
                    "failed_ids": [r["id"] for r in results if not r["pass"]],
                    "max_llm_calls": max(r["actual"]["llm_calls"] for r in results),
                    "max_cited_chunks": max(len(r["actual"]["citations"]) for r in results),
                    "latency_target_met": bool(
                        percentile(timings) < 3000
                        and not any(r["actual"]["status"] == "try_again" for r in results)
                    )
                    if args.provider != "fake"
                    else None,
                }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and any(m["passed"] != m["cases"] for m in summary["methods"].values()) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["fake", "gemini", "groq"], default="fake")
    parser.add_argument("--embedding", choices=["hash-test", "minilm"], default="minilm")
    parser.add_argument("--method", choices=["dense", "hybrid", "both"], default="both")
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation"))
    parser.add_argument(
        "--delay", type=float, default=0, help="Free-tier pacing between requests; excluded from latency"
    )
    parser.add_argument(
        "--timeout", type=float, default=2.8, help="Use 12 only for a separately labelled provider diagnostic"
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if a gold case fails; default always records measurements",
    )
    sys.exit(evaluate(parser.parse_args()))
