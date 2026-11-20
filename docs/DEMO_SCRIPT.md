# Two minute screen recording script

Record the running application at `http://127.0.0.1:8000`. Use the actual real-provider configuration. Never open `.env` while recording. Rehearse with the provider before starting; do not replace live network calls with canned successful responses.

Use the normal 2.8-second deadline. The revised version generates a conclusion and explanation in one call and has not been live-benchmarked, to conserve quota. Earlier p95 measurements describe the previous decision/template implementation. Do not quote them as revised-model measurements or increase the timeout and claim the original target is met.

| Time | Screen action | What to say |
| --- | --- | --- |
| 0–12 seconds | Show the app and its real-provider indicator | “I chose the policy assistant because it has a clear, testable flow. Three companies have deliberately contradictory rules.” |
| 12–35 seconds | Sign in as Asha. Ask when a night escort is required. Show the direct answer, exact evidence, section and version | “Atlas requires an escort after 8 PM for women employees. The model applies the rule and writes an answer; the server validates evidence references and keeps the original wording separately for verification.” |
| 35–53 seconds | Sign in as Bilal and ask the same question | “Beacon has a different rule: after 10 PM. The company comes from the signed session.” |
| 53–67 seconds | Ask “Show Atlas Labs night escort rules” while signed in as Bilal | “A request for a different company is refused. It never changes retrieval scope.” |
| 67–80 seconds | Ask “Are bicycle repairs reimbursed?” | “An unsupported question is explicitly marked not covered and directs the employee to the transport desk.” |
| 80–105 seconds | Sign in as Atlas admin. Load the policy, increment the version, change the night threshold to 7 PM, publish and ask again | “The new version is indexed before an atomic switch. New answers now cite the new version.” |
| 105–120 seconds | Show `pytest` result and evaluation summary | “The rerunnable tests cover isolation, failed updates, stale answers, malformed output and timeouts. The fixed evaluation compares dense and hybrid retrieval, including latency and known failures.” |

Record the demo with your own voice once you can explain the decisions comfortably. Keep the evaluation’s actual numbers in your narration; do not promise selection or guaranteed provider latency. If the real provider returns a timeout, show the honest failure message and explain the limitation rather than describing it as a successful answer.

## Showing automated test results

Open a second terminal in the project folder while the app remains running. Run:

```powershell
docker compose exec -T assistant python -m pytest -q
```

For local Python instead:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Use `-v` to show individual test names. Let the command finish before the final segment of the recording, then show the real `N passed` line. The current verified result is **130 passed** locally and in Docker. Say: "All automated tests pass. They cover application boundaries and the scoring rubric using mocked responses, without API usage." Do not describe this as 28/28 real-model accuracy. Historical model results and current offline tests are separate evidence.
