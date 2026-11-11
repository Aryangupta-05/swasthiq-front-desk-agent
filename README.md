# Sunrise Clinic Front Desk

A Python appointment agent with a React handoff workspace. The tool layer owns every patient, slot and appointment claim. Clinical routing happens before any mutation. This is a synthetic evaluation simulator, not a clinical service.

## Run

Prerequisites: Python 3.11+ and Node.js 24+ with npm. From the repository root:

```sh
python run_local.py
```

Open **http://127.0.0.1:8000**. The launcher installs missing pinned runtime packages, installs the locked frontend packages if needed, builds React and starts the API. No model key is needed to use the deterministic policy. Click **Run supplied samples** to populate the queue using actual backend executions; an empty database contains no fabricated history.

Docker alternative:

```sh
docker compose up --build
```

The named volume preserves local handoff history. Evaluation calendars always reset. See `TEST_RESULTS.md` for exactly which host/container commands were actually verified.

Manual fallback:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

## Model configuration

Copy `.env.example` to `.env`, configure `GEMINI_API_KEY` locally, and set `GEMINI_ENABLED=true` only when real inference is wanted. Never put a key in the browser or Git. The configured adapter uses **Gemini 3.1 Flash-Lite**, Google's supported `generateContent` REST API, JSON response schema, temperature zero, maximum 256 output tokens, a 12-second timeout, and an in-process 32-call budget. No provider-side conversation history is created by the application.

The model is a bounded clinical-risk extractor. It cannot call tools or choose IDs, slots, ownership or final confirmations. Its risk must conform to a strict local schema, and any risk evidence must occur literally in a caller turn. Explicit emergency/injection rules precede inference. Missing key, invalid output, exhausted budget, timeout and provider HTTP errors all retain the deterministic policy and expose the actual provider status in conversation detail. The rules-only path is never described as model usage.

Gemini 3.1 Flash-Lite returned a validated real extraction during verification. Earlier attempts using the Interactions endpoint encountered 503/timeouts; that transport was replaced before release. See the model report, per-conversation metrics and publication state in `TEST_RESULTS.md`, `evidence/` and `DELIVERY_STATUS.md`. No estimated token usage is reported. On a failed call where usage is unavailable, contract `tokens=0` is best-effort **unavailable usage**, not proof of zero billed tokens. On a validated cache hit, tokens are zero because that request made no inference.

Provider references verified during implementation: [text generation](https://ai.google.dev/gemini-api/docs/text-generation?generate-content=true), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output?generate-content=true).

## Contract

```http
POST /agent/run
Content-Type: application/json
```

```json
{
  "conversation_id": "reviewer-example",
  "today": "2026-10-01",
  "turns": [
    "Book Dr. Rao on Saturday at 11:30 am.",
    "Harpreet Singh, 9812200311."
  ]
}
```

With extraction disabled, a successful response has this shape (latency is measured and will vary):

```json
{
  "conversation_id": "reviewer-example",
  "tool_calls": [
    {"name": "search_slots", "arguments": {"doctor_id": "dr_rao", "date": "2026-10-03"}},
    {"name": "lookup_patient", "arguments": {"name": "Harpreet Singh", "phone": "9812200311"}},
    {"name": "book_appointment", "arguments": {"patient_id": "pt_0013", "actor_id": "pt_0013", "doctor_id": "dr_rao", "date": "2026-10-03", "start": "11:30"}}
  ],
  "terminal_state": "booked",
  "escalation_reason": null,
  "patient_id": "pt_0013",
  "appointment_id": "ap_0026",
  "reply": "Appointment ap_0026 booked: Dr. Anjali Rao, 2026-10-03 at 11:30 (Asia/Kolkata).",
  "metrics": {"turns": 2, "tokens": 0, "latency_ms": 5}
}
```

The metrics above are illustrative, not a benchmark. Measured sample metrics are in the evidence report. Required fields are always present. Terminal states are exactly `booked`, `rescheduled`, `cancelled`, `escalated`, `refused`, `abandoned`. Escalation requires one of `clinical_urgent`, `medical_advice`, `not_authorised`, `ambiguous_patient`, `out_of_scope`; all other outcomes have a null reason. Strict models reject extra fields, invalid dates and non-string turns with actionable HTTP 422 details.

## Architecture and tools

```text
React production bundle
  └─ same-origin FastAPI
       ├─ POST /agent/run → complete-script safety preflight
       │    → optional structured risk extraction
       │    → deterministic identity / intent / date policy
       │    → six validated tools → private SQLite snapshot
       └─ UI history / Resolve → separate SQLite database
```

| Tool | Grounded behaviour |
|---|---|
| `lookup_patient` | Returns matching candidates and owned active appointments; never picks an ambiguous candidate |
| `search_slots` | Validates doctor/date, holiday/leave/weekdays, window union and existing occupied intervals |
| `book_appointment` | Requires uniquely resolved actor/target, listed authority, valid free interval and atomic commit |
| `reschedule_appointment` | Requires ownership; one transactional update preserves ID and rolls back on failure |
| `cancel_appointment` | Cancels only an owned active appointment; no bulk capability |
| `escalate_to_human` | Produces a pending human-review record with an exact contract reason; sends no external messages |

`BEGIN IMMEDIATE` and SQLite triggers prevent doctor **or patient** overlaps across separate connections to one shared schedule. Each evaluation request owns a fresh database, so unrelated evaluations deliberately can book the same source slot. See `DECISIONS.md` for this distinction, authority assumptions, source inconsistencies, date/correction semantics and limitations.

UI routes: `GET /api/samples`, `POST /api/run`, `GET /api/runs`, `GET /api/runs/{run_id}`, `POST /api/runs/{run_id}/resolve`, `GET /health`. The grading route adds no wrapper. Tool calls in the transcript are actual calls in execution order, including failures. The UI labels the batch preflight and does not fabricate intermediate dialogue. Determinism shows observed fingerprints, and only labels stable after at least three observed identical requests.

## Verify

```sh
python -m pip install -r requirements-dev.txt
python scripts/validate.py
```

This runs unit/integration tests, backend lint, the production frontend build, and both sets of scripts three times against a fresh local API, then compares their expected blocks. It deliberately disables Gemini to make a reproducible offline regression baseline.

For a separately started API, run the original supplied harness **unchanged**:

```sh
python runner.py --url http://localhost:8000/agent/run
python runner.py --repeat 3 --out results/supplied
python scripts/compare_results.py --out results/supplied --report evidence/supplied.json
python runner.py --dir adversarial --repeat 3 --out results/adversarial
python scripts/compare_results.py --dir adversarial --out results/adversarial --report evidence/adversarial.json
```

The original runner does not grade expected outcomes and does not fail its exit code for fingerprint instability. The separate comparator does both. Pytest also checks actual important patient/date/time results, not merely tool names and terminal states.

Browser checks require a running production app:

```sh
python -m playwright install chromium
python scripts/browser_check.py
```

Frontend source checks: `cd frontend`, then `npm run lint` and `npm run build`. A clean browser test reports its checks and screenshots in `evidence/browser/`.

## Delivery and deployment

Public repository, live application, video and email status are listed in `DELIVERY_STATUS.md`, with verified links only. The public release archive excludes `.env`, SQLite files, original confidential documents, node_modules and virtual environments. The actual coding prompts are in `AI_TRANSCRIPT.txt`, with credentials redacted.

Deploy the repository as one **free Render Docker web service**, branch `main`, Dockerfile `./Dockerfile`, health endpoint `/health`, bind to `$PORT`. No database service is needed. Gemini secrets belong in hosting environment settings; never in build arguments or frontend variables. The same service serves both UI and API, so there is no frontend API URL to configure.

Free-host SQLite history is ephemeral across restart, redeploy and idle spin-down. Local host/Compose history persists. A public Resolve action is a simulator review marker, not authenticated clinical activity. [Render free-service limitations](https://render.com/docs/free) were verified during deployment preparation. No paid resource or managed database is part of this project.

The failure-focused recording script, reproduction steps and limitations are in `VIDEO_SCRIPT.md`. `SUBMISSION_EMAIL.txt` is a draft only. Human hours and assignment deadline remain unknown unless the user supplies them; neither is invented.
