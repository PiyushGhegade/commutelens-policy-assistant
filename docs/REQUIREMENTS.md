# Case study B requirement mapping

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Python, FastAPI, Chroma, embedding model, LLM, JWT | `app/`; local ONNX MiniLM embeddings; Gemini or Groq provider | `/health`; real-provider evaluation |
| Three fictional, contradictory policies | `policies/atlas.json`, `beacon.json`, `cedar.json` | Same question produces different night, weekend, airport and no-show rules |
| Current version only | SQLite active revision points to an immutable Chroma collection | `tests/test_versions.py` |
| Failed ingestion cannot half-update | Stage entire index before committing pointer | Failed embedding and partial-write tests |
| Company from JWT; no client override | Signed fixed-algorithm JWT; strict question schema | `tests/test_security.py` |
| Retrieval restricted on server | Collection resolved by signed company; metadata `where` filter and recheck | Company-specific answer tests and poisoned-metadata test |
| Grounded answers and checkable citations | Model-generated verdict and explanation; separate exact source text and trusted citations | Mocked examples and response validation; revised live semantics unmeasured |
| Missing evidence means not covered | Structured abstention with transport-desk direction | Gold set negative and compound cases |
| Retrieved instructions cannot grant authority | No model tools; structured response; admission filter; scoped retrieval | Document-injection and model-output tests; documented semantic limitations |
| Retrieval and model failures give clear retry | Separate bounded retrieval and total deadline; plain errors | `tests/test_failures.py`, `tests/test_provider.py` |
| At least ten verified evaluation questions | 28 fixed manually authored cases | `evaluation/questions.jsonl`; generated results contain all six required fields |
| Retrieval and answer quality scoring | Recall@3, MRR@3, exact sections, expected verdicts, named fact/condition alternatives, contradiction guards, citations and abstention | `evaluation/run.py`; evaluation report |
| p95 under three seconds including LLM | Default 2.8-second deadline; one combined generation call | Revised path not live-benchmarked; previous p95 2.03 seconds is historical only |
| At most two LLM calls and three chunks | Two-attempt loop with one overall deadline; evidence capped at three | Recovery/deadline tests and generated maximum counts |
| Bonus retrieval improvement measured | BM25 + dense reciprocal rank fusion | Same gold set and alternating dense/hybrid order; before/after results |
| One-command startup | `docker compose up --build` or Windows `./run.ps1` | Both paths verified; healthy rebuilt Docker container and recorded container tests |
| README and trade-offs | `README.md`, `docs/VIVA_GUIDE.md` | Reviewable design and limitations |
| Two-minute screen recording | You will record it with your own voice; `docs/DEMO_SCRIPT.md` | Prepared screen sequence and speaking points |
| GitHub repository link | Git-ready source with secrets excluded | Publish through your GitHub account before submission |
