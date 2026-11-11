"""Verify public UI history is grounded in the remote runner's observed results."""

import argparse
import json
import sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.models import RunResult  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=30) as client:
        response = client.get("/api/runs")
        response.raise_for_status()
        records = response.json()["runs"]
        summary = []
        for directory in ["remote-supplied", "remote-adversarial"]:
            for path in sorted((ROOT / "results" / directory).glob("*.run1.json")):
                observed = json.loads(path.read_text(encoding="utf-8"))
                matches = [r for r in records if {k: r[k] for k in RunResult.model_fields} == observed]
                assert matches, f"No public backend history matches {path.stem}"
                detail_response = client.get("/api/runs/" + matches[0]["run_id"])
                detail_response.raise_for_status()
                detail = detail_response.json()
                trace_calls = [
                    {"name": e["name"], "arguments": e["arguments"]} for e in detail["trace"] if e["type"] == "tool"
                ]
                assert trace_calls == observed["tool_calls"], f"Incorrect trace order: {path.stem}"
                non_success = observed["terminal_state"] in ["escalated", "refused", "abandoned"]
                assert detail["schedule_unchanged"] == non_success, f"Schedule mutation mismatch: {path.stem}"
                summary.append(
                    {
                        "id": observed["conversation_id"],
                        "state": observed["terminal_state"],
                        "schedule_unchanged": detail["schedule_unchanged"],
                        "tool_trace_matches": True,
                        "model": detail["model"],
                        "metrics": observed["metrics"],
                        "determinism": detail["determinism"],
                    }
                )
        assert len(summary) == 23
        (ROOT / "evidence" / "remote-trace-summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print("23/23 public backend traces match actual runner output and schedule mutation invariants")


if __name__ == "__main__":
    main()
