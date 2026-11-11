"""Check the expected blocks the original runner deliberately does not grade."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.models import RunResult  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="conversations")
    parser.add_argument("--out", default="results/supplied")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--report", default="evidence/expected-report.json")
    args = parser.parse_args()
    rows = []
    for path in sorted(Path(args.dir).glob("*.json")):
        script = json.loads(path.read_text(encoding="utf-8"))
        failures = []
        fingerprints = set()
        metrics = []
        for repeat in range(1, args.repeat + 1):
            result_path = Path(args.out) / f"{script['id']}.run{repeat}.json"
            try:
                result = RunResult.model_validate_json(result_path.read_text(encoding="utf-8")).model_dump()
                expected = script["expected"]
                names = {c["name"] for c in result["tool_calls"]}
                assert result["conversation_id"] == script["id"], "conversation_id differs"
                assert result["terminal_state"] == expected["terminal_state"], "terminal_state differs"
                assert result["escalation_reason"] == expected["escalation_reason"], "escalation_reason differs"
                assert set(expected["must_call"]) <= names, "required tools missing"
                assert not set(expected["must_not_call"]) & names, "forbidden tools called"
                assert result["metrics"]["turns"] == len(script["turns"]), "incorrect turn count"
                fingerprints.add(json.dumps([result["terminal_state"], result["escalation_reason"], sorted(names)]))
                metrics.append(result["metrics"])
            except (OSError, ValueError, AssertionError) as e:
                failures.append(f"run {repeat}: {e}")
        if len(fingerprints) != 1:
            failures.append("fingerprints missing or unstable")
        row = {
            "id": script["id"],
            "passed": not failures,
            "runs": args.repeat,
            "errors": failures,
            "metrics": metrics,
            "fingerprints": sorted(fingerprints),
        }
        rows.append(row)
        print(
            f"{'PASS' if row['passed'] else 'FAIL'}  {script['id']}  {script['expected']['terminal_state']:<11} {script['expected']['escalation_reason'] or '-':<18} {args.repeat} runs, {len(fingerprints)} fingerprint(s)"
        )
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"passed": sum(r["passed"] for r in rows), "total": len(rows), "rows": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n{sum(r['passed'] for r in rows)}/{len(rows)} expected outcomes passed")
    return 0 if rows and all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
