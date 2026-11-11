# Decisions and acceptance contract

## Audit and scope

Read all six brief pages (including both page-four UI images), the entire synthetic clinic, all 15 scripts and expected blocks, the original runner and schema. The schema is binding. Original input files remain in Downloads; the public project includes the necessary synthetic clinic/conversations and the unchanged replay runner, but not the confidential PDF, ZIP or original prose documents. The master coding prompt is included as required, with credentials redacted.

Acceptance gates: strict `/agent/run`; six grounded tools; urgent-before-mutation; unambiguous identity and listed guardians; all 15 outcomes and exact important slots; eight new adversarial scripts with three repeats; transactional concurrency and isolated evaluation; two functional React screens; real metrics and honest publication status. Safety precedes correctness, determinism, restraint, engineering and efficiency.

Architecture: React → same-origin FastAPI → deterministic policy + bounded optional Gemini triage → validated six-tool dispatcher → request-local SQLite. A separate SQLite database holds UI history and handoff resolution. No managed database or real patient data.

## Reset snapshots versus concurrent bookings

The evaluation contract explicitly requires a fresh exact clinic snapshot for every POST. Thus two evaluation requests may both report `ap_0026` at the same date/time: they are independent simulations, not claims to one live clinic calendar. Each run has its own SQLite database, closed after the result is formed. UI counters persist real simulation runs, not shared clinic appointments.

`Schedule(path)` also supports an explicitly shared SQLite calendar. `BEGIN IMMEDIATE` serializes writers; insert/update triggers reject overlapping active appointments for either the doctor or patient. Tests race distinct connections against the same file and require exactly one winner. This shared-calendar primitive is intentionally not exposed as an unauthenticated public patient-booking API. The supplied evaluation route must never become a shared calendar.

## Commit barrier and honest transcript

Scripts contain all caller turns in advance, rather than reactive dialogue. Every original turn is safety-checked before any mutation, even if the caller later says to ignore symptoms. Tool trace records actual execution order, including failed validation. The UI displays callers first, followed by actual processing events. It explicitly labels the batch safety barrier and does not fabricate questions, confirmations, tool results or interactive timing. Read-only searches may inspect superseded requested dates; only the final corrected preference reaches a mutation.

The reference image shows a search before the emergency arrives, whereas the schema's hard requirement is that no booking proceed during an emergency. We choose the stronger full-script preflight: an urgent script immediately calls only the escalation tool. This changes the example screenshot's event sequence while preserving the same hierarchy and honest inline tool trace.

## Ground truth and sample inconsistencies

The illustrative schema request says `kal` on 1 October (a holiday), but its illustrative response books 3 October for an unrelated patient. It is a shape example, not an expected behavioural fixture. Real scripts and clinic data determine actions. Appointment IDs come from committed SQLite rows; first new ID is `ap_0026` because there are 25 source appointments.

Dr Rao's Monday windows overlap at 11:45. Slots are the sorted set union, not concatenated intervals. All bookings last exactly 15 minutes, must fit a source window and avoid active intervals. A booked patient cannot simultaneously visit another doctor. Cancelled intervals may be reused. Rescheduling is one update inside a transaction; a failure preserves the old appointment and identifier. No-op rescheduling is rejected.

`runner.py` checks a subset of types, required fields and repeat fingerprints, and does not compare expected outcomes. Its exit code also does not fail for fingerprint instability. The separate comparator fails for state/reason/required or forbidden tools, missing repeats, or unstable fingerprints. Pytest additionally asserts actual patient, date, time, ownership, no mutation and stricter response schemas.

## Identity and authority

Patient names and phones are synthetic identification factors, not production authentication. A shared phone is never unique identity. `lookup_patient` returns all matching candidates, and grants no permission to guess. For a write, both actor and target must have been uniquely resolved in the same tool session. A caller can act only for themself or a patient ID explicitly in their source `guardian_of` list. A neighbour, friend, shared surname/phone or asserted consent is insufficient. Tool arguments cannot grant administrative authority; no bulk tool exists.

The brief has no OTP, accounts, authenticated caller IDs or consent workflow. We accept matching full name plus supplied phone for synthetic self-service; production deployment would require verified caller authentication, audit access controls and a clinical escalation integration. The public deployment is expressly a synthetic simulator. Marking a handoff resolved persists a UI review status; it does not mean a clinician was actually contacted. `escalate_to_human` creates an honest pending-human result, not a sent message or clinical intervention.

## Safety, refusal and restraint

Active chest symptoms, breathing difficulty, unconsciousness and other explicit red flags interrupt all administrative intentions. This is triage routing, not diagnosis or clinical advice. Medical judgement and dosage requests route to `medical_advice`. Unauthorised operations, unresolved patient collisions and legitimate unsupported requests use their exact schema reasons. Bulk destruction, data export, instruction replacement and impersonated system roles are refused without a handoff. Empty or incomplete scripts can be abandoned. Known routine work proceeds through the actual tools.

Negation is clause-local; `no chest pain, but cannot breathe` must still escalate. Historic phrases are handled conservatively. Regex coverage is finite, especially nuanced Hindi and indirect symptoms. Optional evidence-validated Gemini triage broadens recognition but is not a clinical guarantee. No claim of passing unseen cases is made.

## Dates, preferences and corrections

Only request `today` determines relative dates and past-date validation. Machine time is used solely for measured latency and UI event timestamps. Clinic wall times use Asia/Kolkata. `kal` means tomorrow in prospective appointment requests; `parso` means two days later. Weekdays mean the next occurrence including today; explicit `next` advances a same-day weekday by seven days. Numeric `tareekh` uses the request month. Invalid dates are never silently normalized. Ambiguous/no usable scheduling information is not invented.

Later scheduling preferences replace earlier ones. `nahi nahi`, `actually`, `instead`, `rather`, `correction` and `make that` delimit corrections within a turn. Morning is before 12:00, evening from 16:00; with no exact time, choose the earliest available qualifying slot. Exact requested times are never silently replaced by a different free time. Future extensions: resolve ambiguous clock conventions with an actual interactive clarification loop and richer date grammar.

## Gemini and determinism

The provider only returns structured `risk` and literal caller `evidence`. It has no tool execution permissions and supplies no patient/slot identifiers or confirmations. Python still enforces every write. Explicit emergency and injection rules run before provider calls, minimizing both risk and cost. Missing credentials, HTTP errors, timeout, malformed/off-schema JSON and ungrounded evidence all fall back to the deterministic policy. Provider status is visible in detail and metrics; it is never represented as successful model usage. Live discovery listed multiple generations; the first transport/model choices produced 404 or 503/timeouts. The released adapter uses the verified working Gemini 3.1 Flash-Lite `generateContent` endpoint rather than keeping a newer but unavailable transport. This choice prioritizes tested functionality and latency.

Temperature is zero. An in-process bounded content cache reuses validated triage on identical turns; cache-hit tokens are zero because no inference was made on that request. Actual provider token totals are reported only when returned, including thinking tokens when present. Latency is measured end-to-end, not a fabricated estimate. Cache is an optimization, not proof of uncached model determinism. Pure-policy tests run without a model; live runner reports document the exact configured mode. A process call budget prevents unlimited public API spending. Model availability can change; configure `GEMINI_MODEL` via `.env`.

## Interface and operational boundaries

Both screens follow the provided hierarchy: shared narrow sidebar, header, four counters, handoff list, Resolve action, and transcript/outcome columns. Counts derive from real backend records. Empty workspace is empty; no sample history is presented as live. Run the supplied scripts explicitly. UI history is bounded to 500 runs; free-host disk state may reset at restart or redeploy. Local SQLite history persists across application restarts. Public resolution is intentionally a simulator action, not authenticated clinical workflow.

One service hosts the production React bundle and API at the same origin, avoiding brittle frontend/backend URL configuration. Docker offers a one-command fresh build; the Python launcher provides a local fallback. Free Render may cold-start. Secrets are local ignored environment files or hosting secrets; never embedded in the frontend. A raw key appeared in the user's instruction; its transcript occurrence is redacted, and the key is excluded from packages and Git.

## Remaining four hours

Prioritize independently reviewed multilingual triage and negation cases, uncached provider repeated-run analysis, real caller verification and audited handoff integration, and richer property-based tests of calendar/identity constraints. These are future work, not implemented claims.
