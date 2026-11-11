# Full flow verification

The reviewer runs a fixed caller script in React, which posts to FastAPI, executes the safety policy and grounded tools in a fresh SQLite calendar, stores UI history separately, and renders the actual transcript and result. Resolve updates the persisted UI record.

| Boundary | Verified evidence |
|---|---|
| Browser renders production assets | Local and public Chromium screenshots; strict TypeScript/build passed |
| Browser → API | Seven browser checks locally and remotely, including a real POST and simulated HTTP failure |
| API → calendar | 74 unit/integration tests; strict validation, exact important slots and identity assertions |
| Calendar integrity | Independent SQLite connections raced one shared file with exactly one winner; failed writes preserve the original rows |
| Evaluation isolation | Repeated identical POSTs create independent `ap_0026` results without cross-request leakage |
| Calendar → result | Tool result forms every confirmation; 23 public trace sequences and schedule mutation flags match actual runner output |
| Result → workspace | Actual outcomes, metrics, tool arguments/results and observed fingerprints; no invented sample counters |
| Resolve → persistence | Browser resolves a real handoff and verifies the stored status after reload |
| Public deployment | Free Render Docker build reached Live; public root and `/health` returned 200 without login |
| Publication | Public GitHub repository and verified 180-second video; no credentials, confidential input documents or database files in tracked releases |

The full test matrix and measured provider statuses are in TEST_RESULTS.md. The original runner alone does not compare expected outcomes, so independent comparisons were required. Three-repeat checks use a bounded model cache; they do not establish uncached provider determinism.

The source audit and tests exposed and corrected evening-slot interpretation, a correction discarding the earlier doctor, an explicitly supplied appointment ID outside caller ownership, a form label lookup, and mobile overflow from an absolutely positioned screen-reader label. A final UX check moved API errors into the open conversation dialog so they remain visible. Provider transport failures were resolved by using verified Gemini 3.1 Flash-Lite `generateContent`, with safe fallback for individual transient failures.

These checks are about the synthetic simulator. There is no real clinician notification, verified caller authentication, managed database, human clinical validation or hidden-set score. Free-host SQLite history can reset across service restart, idle spin-down or redeployment.
