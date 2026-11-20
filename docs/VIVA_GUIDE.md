# Viva preparation for Commute Policy Assistant

## Why I chose case study B

I chose B because the main flow is small enough to explain and change confidently: authenticate, retrieve the current company policy, apply the rules, and return an answer with citations. A needs durable approval workflows and seat concurrency. C needs a much larger database and a secure SQL execution system. B lets me spend more time proving correctness and testing failure behaviour.

## My opening explanation

“I built a policy assistant for three fictional companies whose rules deliberately disagree. The JWT decides the company. Chroma retrieves only that company’s active revision. The LLM applies the retrieved rules and generates a conclusion. Python validates the schema and evidence IDs and supplies exact citations. Exact source quotations appear separately as evidence. A new policy is indexed separately and activated only after it is readable in full. My evaluation uses the same fixed questions for dense and hybrid retrieval.”

## The flow I can draw in thirty seconds

```text
Employee question + signed JWT
             |
             v
FastAPI validates JWT and input
             |
             v
SQLite resolves this company's active revision
             |
             v
Chroma dense retrieval -> optional BM25 rank fusion
             |
             v
One LLM call selects evidence and writes a grounded conclusion
             |
             v
Python validates IDs + rechecks active revision
             |
             v
Model-written answer + separate exact quotations and citations
```

## Where to start reading the code

| File | What I should understand |
| --- | --- |
| `app/models.py` | Input limits and the tiny schema the LLM must return |
| `app/auth.py` | Signed JWT, fixed algorithm, expiry, issuer, audience, company and role |
| `app/store.py` | Complete policy revisions, staging index, atomic active pointer |
| `app/retrieval.py` | Dense search, tenant filter, metadata recheck, BM25 and rank fusion |
| `app/llm.py` | General grounding prompt, structured generation and safe error categories |
| `app/answers.py` | Verdict prefix and citation-number rendering; no policy templates |
| `app/main.py` | The complete request flow, deadline and answer rendering |
| `evaluation/run.py` | Fixed gold answers, answer checks and latency measurements |

Read in this order. Start by understanding the flow; then trace one question through the files. Every added component should have a reason you can state in one sentence.

## Questions I should be ready to answer

**What is RAG?** Retrieval augmented generation finds relevant source material before asking the model to respond. Here the model applies the current company's rules and generates an answer with exact policy text separately available for checking.

**What does the LLM do, and what does Python do?** The LLM understands the question, applies scenario facts to policy conditions and writes the explanation. Python verifies identity and scope, manages revisions, validates the response and supplies trusted citation metadata. It does not independently prove the model's interpretation.

**Why are answer and evidence different?** The answer explains what the rules mean for the scenario; evidence preserves the original wording. For the airport example, the intended conclusion is No: INR 1,800 is INR 300 above a INR 1,500 cap even with approval. Missing gender or other necessary employee facts must stay conditional.

**Are replies hardcoded to the examples?** No. One general prompt and schema apply across policy wording and section names. There are no section-specific answer functions or stored sample responses in the production path. Injected test responses are test data, not production answers.

**Does an exact quote guarantee that the answer is correct?** No. It guarantees the returned text exists in the cited source. The model can still choose an irrelevant section or miss a condition. That is why the gold set measures answer relevance, correct abstention and compound questions, alongside citation validity.

**Can the user ask for another company?** They can type anything. The question payload has no company field. The server resolves the collection using the verified JWT and filters by that company and version. Known foreign company names also trigger an early refusal, but that name check is not the isolation boundary. Even an obfuscated name cannot change the collection being queried.

**What if a retrieved document says to ignore instructions?** It cannot grant access to another collection or make the application run tools. A simple admission filter rejects recognizable assistant-directed instructions, and the model is told to treat policy text as data. The filter is not a complete injection detector. A malicious administrator could still publish false policy facts, so trusted policy ownership remains necessary.

**Why SQLite and Chroma?** Chroma stores and searches embeddings. SQLite provides a tiny, transactional registry of the one active revision for each company. They do different jobs; I do not pretend they share a distributed transaction.

**How does atomic ingestion work across two stores?** Build a new immutable Chroma collection first. Check it is complete. Then atomically change the SQLite pointer. On a failed build, the pointer stays unchanged. A process crash can leave an unused collection, which is a cleanup problem rather than a half-live policy. A crash after the pointer commits means the new version is active even if the client never received the acknowledgement.

**What about a question already in flight when a new version activates?** The server checks the active pointer again after the LLM returns. If it changed, it discards the answer and asks the employee to retry. In this single-worker demo no asynchronous yield occurs between that check and response construction. Stronger multi-process linearizability would require a wider coordination mechanism.

**Why use generation instead of Gemini Decision?** Choosing a source section alone does not apply the rule to a user's situation. The revised design generates a conclusion and explanation in one call. The earlier decision-only design was faster in a recorded run but relied on limited answer templates.

**How do you conserve quota?** One call combines selection and answer generation, capped at 512 output tokens. There are no automatic retries or second grading calls. This revision was tested locally without live API calls. The 2.8-second overall deadline remains in place.

**How do you know the revised model is correct and fast?** Mocked tests establish application behaviour, not remote model semantics. Previous live results belong to the old design. Revised live accuracy and p95 remain unmeasured until I choose to spend quota on a real run.

**Why verify index reads before activation?** An earlier validation run exposed a Chroma error where a collection had the expected record count but its HNSW reader failed. Small-policy writes now persist immediately, and a complete scoped vector query must work before activation. A failed probe leaves the previous policy active.

**How does hybrid search work?** Dense embeddings rank semantic similarity. BM25 ranks literal term matches. Reciprocal rank fusion adds `1 / (60 + rank)` from each ranking. Only the top three fused results go to the LLM. It avoids trying to compare cosine similarity directly with BM25 scores, which use different scales.

**Did hybrid search improve results?** Read the generated evaluation report and give its actual numbers. A small eight-section document may already be solved by dense search. An unchanged score, or a regression, is a useful result. Do not say “hybrid is better” unless the measurements support it.

**How did you verify the answers?** I read each fictional policy and wrote expected section IDs and key facts before running the evaluator. Rubric v2 checks the expected verdict, named fact/condition patterns, known contradictions, status, exact selected sections, citation validity, scope and budgets. Equivalent wording is accepted through curated alternatives and normalization; unknown phrasing still needs human review. It does not use the same LLM to grade itself.

**Why are fake LLM tests useful?** They reliably reproduce malformed outputs, quota errors, timeouts and other edge cases without an API key. They prove application behaviour. They do not prove that the real model understands policy questions.

**What does p95 mean?** Sort measured request times. At least 95% are at or below the p95 value. This project uses nearest rank, includes the LLM and local API overhead, and reports failures separately. A quick timeout is not counted as successfully meeting the answer requirement.

**What is deliberately out of scope?** PDF/OCR ingestion, a production identity provider, distributed workers, multilingual evaluation, and verified employee-profile integration. Explicit scenario facts are applied; missing attributes remain conditional.

## Small changes to practise live

1. **Change an escort cutoff.** Sign in as `atlas-admin`, load the current policy, increase the version, change “after 8 PM” to “after 7 PM”, and publish. Ask the same question again. Show the new version and quote. The model and application code do not change.
2. **Change the demo token lifetime.** In `app/auth.py`, change 30 minutes to 15. Explain that existing tokens retain their original signed expiry and newly issued tokens use the new expiry.
3. **Tune hybrid weighting.** In `app/retrieval.py`, multiply the lexical contribution by a small weight. Rerun the same evaluation. Explain the trade-off between exact terms and paraphrases; keep the gold set unchanged.
4. **Add an uncovered question.** Add one JSONL line with a manually checked `not_covered` expectation and run evaluation. Do not change the application merely to hardcode that question.
5. **Change the deadline.** Adjust `ANSWER_TIMEOUT` locally and rerun a live evaluation. Show the effect on successful answers, timeouts and p95. A larger deadline must not be presented as meeting the original three-second target.

## A fifteen minute practice session

Spend two minutes explaining the flow, three minutes tracing authentication and isolation, three minutes explaining atomic updates, three minutes running tests and interpreting evaluation, and four minutes making one small change. If you cannot explain a helper or a dependency, read it before the viva. Avoid claiming production guarantees that this demonstration does not implement.
