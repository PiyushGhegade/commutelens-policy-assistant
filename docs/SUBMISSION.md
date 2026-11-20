# Submission checklist

## Repository contents

- One-command startup with Docker Compose and a Windows launcher.
- Required FastAPI, Python, Chroma, embedding model, LLM and JWT stack.
- Three fictional policies with contradictory rules and a complete update example.
- Automated tests plus a fixed 28-question gold set.
- Generated evaluation JSONL rows in the required six-field format.
- README, architecture/trade-offs, evaluation report, requirement mapping and viva guide.
- Two-minute demo sequence and speaking points. You will record the running real-provider app with your own voice.

## Before sending the submission

1. Read `docs/EVALUATION_REPORT.md`, including actual known failures. Do not describe the fake model's runtime as real LLM latency.
   The revised generation path has not been live-evaluated, to conserve quota. Earlier 28/28 and p95 2.03-second results describe the previous design only. Do not present them as revised-model measurements.
2. Run `docker compose up --build` on a machine with Docker Desktop running, or use the verified Windows launcher. Local tests need no API key. Run live evaluation only when you choose to spend the associated quota.
3. Use a free-tier key to rehearse the real-provider demonstration. Check the provider indicator and citations. Never put a key in a source file or recording.
4. Record your own two-minute narrated explanation. Follow `docs/DEMO_SCRIPT.md`.
5. Publish the source to the public repository `PiyushGhegade/commutelens-policy-assistant`, including the README diagrams and evaluation artifacts. Verify the published files before sending its link to reviewers.
6. Verify that `.env`, `.venv`, `data`, browser recordings under temporary directories and original assignment documents are excluded. `.env.example` is safe to include.
7. Open the published repository URL in a fresh browser, verify the README and recording are available, and send that link before the deadline in the email. The email and deadline were not included in the provided workspace.
8. Practise explaining every module and making one live change before the 15–20 minute viva. Use the short reason for choosing B from the viva guide.

Passing the local checks is evidence of implementation quality, not a guarantee of selection. The brief gives greater weight to the viva than repository size or the number of frameworks.
