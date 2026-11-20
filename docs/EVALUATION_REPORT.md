# Evaluation of Commute Policy Assistant

## Current revision: general responses and scoring rubric v2

**130 automated tests passed locally in 21.44 seconds and in Docker in 11.13 seconds.** This includes 42 scoring regression tests. Lint checks pass. Reports: `artifacts/tests.xml` and `artifacts/docker-tests.xml`. No live LLM calls were made.

The application generates a verdict and concise answer points with referenced section IDs in one LLM call. Python validates the structure and builds trusted citations. Normal requests do not retry automatically.

The current scorer explicitly checks verdicts, essential conditions/facts, known contradiction patterns, evidence, scope, call limits and direct presentation. Number words, thousands separators, hyphens, and time punctuation are normalized. Curated regex alternatives allow selected equivalent wording. This is a deterministic rubric, not unrestricted semantic grading: novel paraphrases, negation and contradictions outside the curated patterns still need human review.

All 28 original question inputs remain unchanged. Gold expectations now include `verdicts`, named `facts`, `forbidden` patterns and `rubric_version=2`. Legacy substring expectations are retained as `legacy_contains` for provenance, not used for current scoring. Verdicts such as conditional or yes-with-conditions may both be accepted where appropriate, but the required conditions must still be stated. Current scores are therefore not directly comparable with historical rubric-v1 scores.

The scorer regression tests use manually written example responses for the existing questions. They verify that valid alternative wording passes, wrong verdicts fail despite correct citations, missing conditions fail, and known contradictions fail. Saved-response rescoring never invents missing verdicts or modifies the original file. These are evaluator tests, not real-model accuracy results.

No live Gemini or Groq requests were made for this change. Current model accuracy and real-provider p95 remain unmeasured. Historical 28/28 results below describe older implementations and rubric versions. A configured 2.8-second deadline is not proof of successfully meeting the three-second answer target.

## Historical results: previous decision/template implementation

The previous implementation passed **108 automated tests on Windows and 108 in Docker**. The latest direct-answer evaluation on 21 November 2026 IST passed **28/28 cases under the normal 2.8-second deadline**, with measured end-to-end **p95 2,030.44 ms**. It used real Gemini calls, real MiniLM embeddings and no answer cache. All 20 answered responses are distinct from their full source quotations, and all citations match the policy text. The exact Saturday-and-cutoff question from the browser screenshot passed through the rebuilt Docker app in **1,003.97 ms**, returning a concise answer with two separate evidence citations.

**The latest recorded run meets the three-second p95 target.** This is a 28-case sequential local test, not an unconditional availability or latency guarantee for a free remote provider. Earlier failure results are retained below, including the original 8,365.30 ms diagnostic and an intermediate run that exposed an index-readiness problem.

## Environment and method

Measurements include the original 18 November run and the recovery run on 21 November IST using Windows 11, Python 3.12.13, FastAPI 0.164.0, Chroma 1.5.9 and local ONNX `all-MiniLM-L6-v2` embeddings. The original selector was `gemini-3.5-flash-lite`. The current primary selector is `gemini-decision-1`, with one bounded Flash-Lite fallback. Runtime/test dependency versions are pinned in `requirements.txt`. The fixed gold set still contains the same 28 questions over three eight-section fictional policies; no gold expectations were altered to obtain the passing result.

Expected statuses, section IDs and key facts were written by checking the supplied fictional policies before running evaluation. No grading LLM is used. Each case checks status, the exact selected section set, required facts, citation fidelity, signed company scope and the call/chunk limits. An abstention must contain no citations and must direct the employee to the transport desk.

The evaluator invokes the actual FastAPI routes through a local ASGI test client. Wall time starts immediately before the API request and includes JWT processing, retrieval, embedding inference, the provider HTTP call and answer construction. It excludes one-time model/index warmup and external quota-pacing delays. This is a sequential local-machine measurement, not a production load test or browser/network benchmark. The first provider connection is included. p95 uses the nearest-rank definition. The test set is small and intentionally adversarial; it is not a representative statistical estimate of employee question accuracy.

## Automated tests

`python -m pytest -q --junitxml=artifacts/tests.xml` produced **108 passed in 20.22 seconds**. That report has since been replaced by the current 88-test run in `artifacts/tests.xml`.

The rebuilt Docker image started a healthy service on localhost. The same suite passed **108 tests in 11.17 seconds** inside the Linux container using Python 3.12.16; `artifacts/docker-tests.xml` now contains the current 88-test Docker run. An earlier download-free fake-provider/hash-embedding evaluation also ran in Docker; those deliberately weaker test-double results are saved separately in `artifacts/docker-smoke/` and are not used as real-model quality evidence.

The suite exercises missing/expired/forged tokens, scope overrides, contradictory company answers, admin permissions, failed/partial ingestion, unreadable staging indexes, single-section restart persistence, concurrent publishers and stale in-flight answers. Recovery tests verify finite evidence choices, confidence/probability validation, malformed/uncertain decisions, bounded fallback, shared deadlines and safe logging. Composition tests cover compound-question order, all three companies' conditions, strict time boundaries, no gender inference, midnight ambiguity, changed source values, unparsed qualifications, focused answers and exact evidence kept separate from response wording.

Tests use real Chroma, deterministic test embeddings and fake model outputs. They run without API keys or network access. They establish application behaviour under those scenarios, not the semantic accuracy or performance of a remote LLM.

The browser smoke check passed login, a company switch, citations, a cross-company refusal, current source display, publishing a higher version and receiving an answer from it. Desktop 1440 px and mobile 390 px layouts were checked for horizontal overflow and JavaScript errors. The UI check used a clearly labelled fake model to avoid consuming real-provider quota.

## Bonus comparison on the same 28 questions

Both retrieval methods use the same real MiniLM embeddings, policy chunks and gold set. The baseline sends the top three dense results to the selector. The hybrid method fuses up to six dense candidates with BM25 rankings using reciprocal rank fusion, then sends its top three. Dense/hybrid order alternates per question.

The comparison below uses a fake overlap selector so that retrieval can be compared reproducibly without remote API variance. These are **not real-LLM answer-quality or latency results**. Raw rows and summaries are in `artifacts/offline/`.

| Metric | Dense baseline | Dense plus BM25 |
| --- | ---: | ---: |
| Cases passing the whole gold check | 25 / 28 | 24 / 28 |
| Retrieval Recall at 3 on 20 answerable questions | 1.000 | 1.000 |
| Retrieval MRR at 3 | 1.000 | 1.000 |
| Citation fidelity among cited responses | 100% | 100% |
| Mean retrieval time across all cases including early refusals | 90.22 ms | 85.94 ms |
| Retrieval p95 | 104.15 ms | 103.91 ms |
| End-to-end p95 with fake selector | 117.24 ms | 116.68 ms |

There is **no measured retrieval-recall gain** on this small corpus. The approximately 4.29 ms mean difference is too small and noisy to claim a speed improvement; hybrid adds BM25 tokenisation, corpus scoring and rank fusion work. Its practical complexity cost is one small ranking pass, one dependency and no extra model call or download. The fake selector performs worse with hybrid because one irrelevant candidate for the driver-contact question shares a word with the question. Dense top-three and hybrid top-three both contain the relevant evidence on every answerable case, so this difference is an answer-selector limitation rather than a retrieval recall improvement.

I would retain dense search as a simpler baseline until a larger, held-out set demonstrates a useful hybrid gain. Hybrid remains selectable in the demo so its measured behaviour can be examined. No gold answers were changed to make the bonus look successful.

Known fake-selector failures are `user-injection`, `compound-covered`, and `compound-missing`, plus `missing-route` for hybrid. The fake selector is intentionally an overlap test double, not a semantic model. The real Gemini run correctly handled all four of those cases when it returned a response.

## Direct-answer revision

The answer area now applies the selected rules and gives a focused response instead of repeating the source paragraphs. Exact quotations remain unchanged in the evidence area. For the supported eight section formats, `app/answers.py` reads values from the active text, applies explicit time comparisons and orders compound answers by the question's topics. It retains approval requirements and gender conditions, and makes no booking or escort-assignment promise. Unknown formats or newly added qualifications that cannot safely be parsed are explicitly labelled as policy excerpts. This is a controlled composer, not unrestricted model-generated prose.

The same frozen 28-question set was run with the real provider under the normal deadline and saved in `artifacts/direct-answers/`. No expected facts were changed. All 28 cases passed, with median **636.43 ms**, p95 **2,030.44 ms**, no error responses, at most two model calls and at most two citations. All 20 answered cases use direct wording rather than copying their complete evidence paragraphs. That presentation check was also applied offline to the saved real responses without making additional model calls.

The reported browser question, "Can I book a cab for Saturday, and how many hours before the trip must I request it?", now produces:

> Yes. Saturday pickups are permitted only with prior line manager approval. [1]
>
> Submit your cab booking or shift-change request at least 2 hours before the scheduled trip. [2]

The answer omits unrelated Sunday/holiday details; the complete source paragraphs remain under the two evidence citations. The exact browser reproduction is saved as `artifacts/direct-answers/browser-case.json`. This local run is useful regression evidence and does not establish universal interpretation accuracy for arbitrary policy wording.

## Earlier recovery evaluation under the normal deadline

Command:

```powershell
.venv\Scripts\python.exe -m evaluation.run --provider gemini --method hybrid --delay 0.5 --output artifacts/gemini-recovery-final
```

The first attempt uses Gemini Decision to choose one of at most eight evidence subsets, including abstention. Probability fields and option IDs are validated. A confidence below 0.85 or a temporary failure permits one Flash-Lite fallback within the remaining total budget. The primary attempt has a 1.4-second ceiling; the complete API call still has the original 2.8-second ceiling. There is no answer cache, canned answer path or third call. Quota/credential errors and malformed outputs are not retried.

| Metric | Current observed result |
| --- | ---: |
| Whole gold check | 28 / 28 |
| Retrieval Recall at 3 and MRR at 3 | 1.000 / 1.000 |
| Negative/cross-company cases passing | 8 / 8 |
| Citation fidelity among cited responses | 100% |
| End-to-end median / p95 | 689.97 ms / 1,707.75 ms |
| Retrieval p95 | 35.82 ms |
| Error responses | 0 |
| Maximum calls / cited chunks | 2 / 2 |

Both `beacon-saturday` and `cedar-sunday` used the fallback after a low-confidence decision and passed. The original failed cases now pass: `beacon-night` in 889.8 ms, `beacon-saturday` in 1,761.8 ms and `cedar-eligibility` in 767.0 ms. Raw rows and the summary are in `artifacts/gemini-recovery-final/`. The browser reproduction is separately saved as `browser-case.json` in that folder.

An intermediate validation run in `artifacts/gemini-recovery/` passed 17/28 because 11 requests hit Chroma's `Nothing found on disk` HNSW reader error for one freshly staged policy. These were retrieval failures, not wrong model answers. Counting records had not proved that the vector index was readable. The fix persists tiny-index writes immediately and requires a complete, tenant-filtered vector query to succeed before activation. The previous policy remains active if that probe fails. The final run above was taken after this storage fix; the failed intermediate results are retained rather than discarded.

References: [Gemini Decisions API](https://ai.google.dev/gemini-api/docs/decisions-api), [free-tier decision pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-decision), [Chroma index configuration](https://docs.trychroma.com/docs/collections/configure). The new path selects evidence using a real model with zero generated output tokens; it does not bypass model judgment. A confidence threshold is a routing heuristic and still requires semantic evaluation.

## Historical generative Gemini diagnostic

Command:

```powershell
.venv\Scripts\python.exe -m evaluation.run --provider gemini --method hybrid --timeout 12 --delay 1 --output artifacts/gemini-quality
```

The run used `GEMINI_MODEL=gemini-3.5-flash-lite`, local MiniLM embeddings, one provider request per non-short-circuited question and no retries or answer cache. Raw rows, including failures, are in `artifacts/gemini-quality/hybrid.jsonl`; the summary is in the same folder. A one-second pacing interval between questions was outside the timed request.

| Metric | Observed result |
| --- | ---: |
| Whole gold check | 25 / 28, 89.29% |
| Provider failures | 3 / 28 |
| Non-error responses matching gold | 25 / 25 |
| Negative and cross-company cases passing | 8 / 8 |
| Retrieval Recall at 3 | 1.000 |
| Retrieval MRR at 3 | 1.000 |
| Answered responses with citations | 17 |
| Citation fidelity among those responses | 100% |
| Maximum LLM calls per question | 1 |
| Maximum cited chunks | 2 |
| Mean retrieval time across all cases | 53.76 ms |
| Retrieval p95 | 111.54 ms |
| End-to-end median | 3,541.95 ms |
| End-to-end p95 including failures | 8,365.30 ms |
| p95 over non-error responses only | 8,222.20 ms |

`beacon-night` and `cedar-eligibility` failed because the provider returned an unavailable response. `beacon-saturday` reached the provider timeout. The API returned `try_again` with no partial answer or citations. A quoted sentence being correct does not establish universal semantic reliability; the conditional 25/25 result is only for this small test set.

An earlier six-question smoke run of `gemini-3.1-flash-lite` under the normal 2.8-second deadline produced no successful answers: availability errors and deadlines dominated. Those results remain in `artifacts/live-smoke/`. A separate three-case 12-second diagnostic for that model also returned availability errors and is retained in `artifacts/gemini-diagnostic/`. The smoke run predates the bounded-thread MiniLM tuning, so its retrieval timing should not be treated as a controlled comparison with the final run. No provider body or API key is included in these artifacts.

This original run identified provider latency/availability as the bottleneck. Raising its timeout demonstrated evidence-selection behaviour but did not satisfy the target. The subsequent recovery change and passing normal-deadline run are documented above. A Groq adapter remains available and unit-tested, but no live Groq performance claim is made.

## Trade-offs and known limits

**Controlled composition instead of unrestricted generation.** The AI chooses applicable evidence, and a source-derived rule composer provides direct wording for supported formats while preserving exact evidence separately. This avoids a new generative call and supports deterministic time comparisons. It is less flexible than free-form prose generation: unknown formats retain a labelled source excerpt. Exact citations do not establish correct rule selection or interpretation; model and composer behaviour still need regression tests.

**Immutable revisions and an atomic pointer instead of distributed transactions.** This makes failed builds and restarts easy to reason about. It retains unused old/staged collections after some failures. A crash after committing activation can lose the acknowledgement while leaving the new version correctly active. The demo uses a single worker; a production multi-worker design would need stronger coordination around in-flight responses and lifecycle management.

**Simple admission filter instead of a claimed complete injection detector.** Known assistant-directed instructions are rejected before activation. Tenant isolation and lack of tools do not depend on the filter. A malicious administrator can still publish false facts, and obfuscated instructions or misleading text are not universally detected.

**Small section-level documents instead of OCR/PDF ingestion.** Stable IDs, short complete rules and preserved exceptions make citations easy to verify. Large documents, tables, multilingual policies and contradictory sections within a single company have not been evaluated.

**One recovery attempt within a fixed deadline.** A decision model avoids generative output latency for a finite selection task. Uncertain decisions may consume a second model request; the same total deadline applies. This improves the observed run while keeping quota and call counts bounded. Long provider outages can still produce a clear retry response.

Windows and Docker startup, the container health check and the tests were verified. The user will record the two-minute demonstration with their own voice. GitHub publication requires their connected account and repository choice.
