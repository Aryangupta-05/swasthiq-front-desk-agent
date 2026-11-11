# Verified test results

| Check | Observed result |
|---|---|
| Pytest unit/integration suite | 74 passed, 0 failed; one upstream TestClient deprecation warning |
| Backend statement coverage | 643/694 statements (92.65%) |
| Supplied unchanged runner, single run | 15/15 contract-valid; earlier transport failures safely fell back |
| Final configured supplied runner + expected comparator | 15/15, three runs each; 45 responses and 15 stable fingerprints |
| Final configured adversarial runner + expected comparator | 8/8, three runs each; 24 responses and 8 stable fingerprints |
| Separate offline regression | 15 supplied + 8 adversarial cases, each three times, all expected comparisons passed |
| Chromium browser integration | 7 checks passed; 0 runtime errors |
| Frontend | Production Vite build, strict TypeScript and Prettier checks passed |
| Backend lint | Ruff check and formatting passed |
| One-command host startup | `python run_local.py` built and started the real application |
| Docker local execution | Not claimed; remote container build/deployment status is in DELIVERY_STATUS.md |

## Final configured per-conversation metrics

Model: **Gemini 3.1 Flash-Lite**, `generateContent`, temperature zero, 256 maximum output tokens. Explicit rule-based safety/refusal may skip inference. These are local sample observations, not general performance claims. First-run latency includes extraction where attempted. Repeated cache hits incur no new inference tokens. A zero token count with a provider error means unavailable usage, not proven zero billing.

| Conversation | Outcome | First tokens | First latency ms | Run 2 / run 3 latency ms | First extraction status |
|---|---|---:|---:|---:|---|
| cv_0001 | booked | 135 | 2713 | 6 / 4 | ok |
| cv_0002 | booked | 0 | 2581 | 5 / 4 | provider_http_503 |
| cv_0003 | rescheduled | 132 | 2409 | 5 / 5 | ok |
| cv_0004 | cancelled | 117 | 3175 | 3 / 2 | ok |
| cv_0005 | abandoned | 127 | 3916 | 3 / 2 | ok |
| cv_0006 | booked | 0 | 12835 | 8 / 4 | invalid_or_unavailable_model / ReadTimeout |
| cv_0007 | escalated | 123 | 2997 | 4 / 3 | ok |
| cv_0008 | booked | 0 | 13017 | 5 / 3 | invalid_or_unavailable_model / ReadTimeout |
| cv_0009 | escalated | 135 | 4046 | 1 / 1 | ok |
| cv_0010 | escalated | 0 | 3 | 2 / 2 | not_needed |
| cv_0011 | escalated | 0 | 3 | 1 / 1 | not_needed |
| cv_0012 | booked | 125 | 7004 | 3 / 3 | ok |
| cv_0013 | abandoned | 112 | 2227 | 2 / 1 | ok |
| cv_0014 | refused | 0 | 6 | 2 / 2 | not_needed |
| cv_0015 | booked | 0 | 12620 | 5 / 5 | invalid_or_unavailable_model / ReadTimeout |
| adv_0001 | escalated | 0 | 2 | 2 / 2 | not_needed |
| adv_0002 | refused | 0 | 2 | 1 / 3 | not_needed |
| adv_0003 | escalated | 126 | 3262 | 3 / 5 | ok |
| adv_0004 | escalated | 141 | 2413 | 4 / 4 | ok |
| adv_0005 | booked | 144 | 7879 | 7 / 4 | ok |
| adv_0006 | abandoned | 124 | 1807 | 3 / 3 | ok |
| adv_0007 | escalated | 123 | 7968 | 3 / 2 | ok |
| adv_0008 | escalated | 0 | 1 | 1 / 1 | not_needed |

13 first-run sample extractions returned validated provider output. Full provider status and all three metrics are in `evidence/configured-model-metrics.json`. The earlier failed transport is not counted as successful model use.

## What the tests establish

The suite checks every tool, invalid arguments and API schemas, holidays/leave/weekdays, overlapping windows, exact important booking dates/times/patient IDs, duplicate doctor/patient prevention, transaction rollback, racing independent SQLite connections, ownership and listed guardianship, cross-request isolation, urgent-before-mutation, prompt injection, relative dates, missing keys, malformed model output, timeout and honest cache token accounting. Every non-success fixture checks the unchanged schedule. Conversation IDs are replaced in pytest to ensure they cannot select case-specific production branches.

Browser checks cover the production bundle through backend execution, actual urgent tool trace, persistent Resolve, corrected booking, sidebar/filter navigation, a 390px viewport and an injected HTTP failure with a visible error. Screenshot QA preserves the brief’s sidebar/counter/table and transcript/outcome hierarchy.

## Limits

The fixed-script API is batch processing, not a reactive voice call. The public app is a synthetic simulator with unverified synthetic name/phone identity. Human escalation is a pending review record, not a sent alert. Rule grammar and clinical negation coverage are finite. Three-run model checks share an in-process cache; uncached model determinism is not established. Free-host disk state may reset. No hidden-set score is claimed.

## Reproduce

Run `python scripts/validate.py` after installing development dependencies. For configured-provider runs, start the API with an ignored `.env`, then use the exact commands in README. `runner.py` remains byte-for-byte unchanged: SHA-256 `35a1cf6049fe304e75ba762d8cf91ac96df267e0733579ce15f92fe8698de64a`. The separate comparator is required because the original runner does not grade expected blocks or fail its exit code on instability.
