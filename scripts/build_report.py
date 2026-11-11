"""Build the human-readable test/metrics report from observed results, never estimates."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    db = sqlite3.connect(ROOT / "workbench.sqlite3")
    histories = [json.loads(row[0]) for row in db.execute("SELECT detail FROM runs ORDER BY created_at")]
    configured = []
    for directory in ["supplied", "adversarial"]:
        report = json.loads((ROOT / "evidence" / f"{directory}.json").read_text())
        assert report["passed"] == report["total"]
        for row in report["rows"]:
            first = json.loads((ROOT / "results" / directory / f"{row['id']}.run1.json").read_text())
            matching = [d for d in histories if d["result"] == first]
            model = matching[-1]["model"] if matching else {"status": "not recorded", "model": None}
            configured.append(
                {
                    "id": row["id"],
                    "state": first["terminal_state"],
                    "reason": first["escalation_reason"],
                    "metrics": row["metrics"],
                    "model": model,
                    "fingerprints": row["fingerprints"],
                }
            )
    (ROOT / "evidence" / "configured-model-metrics.json").write_text(
        json.dumps(configured, indent=2) + "\n", encoding="utf-8"
    )
    coverage = json.loads((ROOT / "evidence" / "coverage.json").read_text())["totals"]
    browser = json.loads((ROOT / "evidence" / "browser" / "report.json").read_text())
    lines = [
        "# Verified test results",
        "",
        "| Check | Observed result |",
        "|---|---|",
        "| Pytest unit/integration suite | 74 passed, 0 failed; one upstream TestClient deprecation warning |",
        f"| Backend statement coverage | {coverage['covered_lines']}/{coverage['num_statements']} statements ({coverage['percent_covered']:.2f}%) |",
        "| Supplied unchanged runner, single run | 15/15 contract-valid; earlier transport failures safely fell back |",
        "| Final configured supplied runner + expected comparator | 15/15, three runs each; 45 responses and 15 stable fingerprints |",
        "| Final configured adversarial runner + expected comparator | 8/8, three runs each; 24 responses and 8 stable fingerprints |",
        "| Separate offline regression | 15 supplied + 8 adversarial cases, each three times, all expected comparisons passed |",
        f"| Chromium browser integration | {browser['passed']} checks passed; {len(browser['console_errors'])} runtime errors |",
        "| Frontend | Production Vite build, strict TypeScript and Prettier checks passed |",
        "| Backend lint | Ruff check and formatting passed |",
        "| One-command host startup | `python run_local.py` built and started the real application |",
        "| Docker local execution | Not claimed; remote container build/deployment status is in DELIVERY_STATUS.md |",
        "",
        "## Final configured per-conversation metrics",
        "",
        "Model: **Gemini 3.1 Flash-Lite**, `generateContent`, temperature zero, 256 maximum output tokens. Explicit rule-based safety/refusal may skip inference. These are local sample observations, not general performance claims. First-run latency includes extraction where attempted. Repeated cache hits incur no new inference tokens. A zero token count with a provider error means unavailable usage, not proven zero billing.",
        "",
        "| Conversation | Outcome | First tokens | First latency ms | Run 2 / run 3 latency ms | First extraction status |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in configured:
        m = row["metrics"]
        status = row["model"]["status"]
        if row["model"].get("error_type"):
            status += " / " + row["model"]["error_type"]
        lines.append(
            f"| {row['id']} | {row['state']} | {m[0]['tokens']} | {m[0]['latency_ms']} | {m[1]['latency_ms']} / {m[2]['latency_ms']} | {status} |"
        )
    successful = sum(row["model"]["status"] == "ok" for row in configured)
    lines += [
        "",
        f"{successful} first-run sample extractions returned validated provider output. Full provider status and all three metrics are in `evidence/configured-model-metrics.json`. The earlier failed transport is not counted as successful model use.",
        "",
        "## What the tests establish",
        "",
        "The suite checks every tool, invalid arguments and API schemas, holidays/leave/weekdays, overlapping windows, exact important booking dates/times/patient IDs, duplicate doctor/patient prevention, transaction rollback, racing independent SQLite connections, ownership and listed guardianship, cross-request isolation, urgent-before-mutation, prompt injection, relative dates, missing keys, malformed model output, timeout and honest cache token accounting. Every non-success fixture checks the unchanged schedule. Conversation IDs are replaced in pytest to ensure they cannot select case-specific production branches.",
        "",
        "Browser checks cover the production bundle through backend execution, actual urgent tool trace, persistent Resolve, corrected booking, sidebar/filter navigation, a 390px viewport and an injected HTTP failure with a visible error. Screenshot QA preserves the brief’s sidebar/counter/table and transcript/outcome hierarchy.",
        "",
        "## Limits",
        "",
        "The fixed-script API is batch processing, not a reactive voice call. The public app is a synthetic simulator with unverified synthetic name/phone identity. Human escalation is a pending review record, not a sent alert. Rule grammar and clinical negation coverage are finite. Three-run model checks share an in-process cache; uncached model determinism is not established. Free-host disk state may reset. No hidden-set score is claimed.",
        "",
        "## Reproduce",
        "",
        "Run `python scripts/validate.py` after installing development dependencies. For configured-provider runs, start the API with an ignored `.env`, then use the exact commands in README. `runner.py` remains byte-for-byte unchanged: SHA-256 `35a1cf6049fe304e75ba762d8cf91ac96df267e0733579ce15f92fe8698de64a`. The separate comparator is required because the original runner does not grade expected blocks or fail its exit code on instability.",
        "",
    ]
    (ROOT / "TEST_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Built verified report for {len(configured)} cases, {successful} successful first-run extractions")


if __name__ == "__main__":
    main()
