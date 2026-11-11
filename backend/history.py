"""SQLite UI history is independent of evaluation schedule snapshots."""

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


class History:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, created_at TEXT NOT NULL,
          request TEXT NOT NULL, detail TEXT NOT NULL, fingerprint TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0)""")
        self.db.commit()

    def add(self, request, detail):
        result = detail["result"]
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    result["terminal_state"],
                    result["escalation_reason"],
                    sorted({c["name"] for c in result["tool_calls"]}),
                ]
            ).encode()
        ).hexdigest()[:16]
        run_id = str(uuid.uuid4())
        with self.lock:
            self.db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,0)",
                (
                    run_id,
                    request.conversation_id,
                    datetime.now(timezone.utc).isoformat(),
                    request.model_dump_json(),
                    json.dumps(detail),
                    fingerprint,
                ),
            )
            # Bound public demo history. This does not mutate evaluation data.
            self.db.execute(
                "DELETE FROM runs WHERE run_id IN (SELECT run_id FROM runs ORDER BY created_at DESC LIMIT -1 OFFSET 500)"
            )
            self.db.commit()
        return run_id

    def list(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            request, detail = json.loads(row["request"]), json.loads(row["detail"])
            result.append(
                {
                    "run_id": row["run_id"],
                    "conversation_id": row["conversation_id"],
                    "created_at": row["created_at"],
                    "excerpt": next(
                        (t for t in request["turns"] if "dard" in t or "pain" in t), " ".join(request["turns"])[:160]
                    ),
                    "resolved": bool(row["resolved"]),
                    "fingerprint": row["fingerprint"],
                    **detail["result"],
                }
            )
        return result

    def get(self, run_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            all_runs = self.db.execute("SELECT fingerprint FROM runs WHERE request=?", (row["request"],)).fetchall()
        return {
            **json.loads(row["detail"]),
            "run_id": run_id,
            "created_at": row["created_at"],
            "resolved": bool(row["resolved"]),
            "determinism": {
                "runs": len(all_runs),
                "fingerprints": sorted({r["fingerprint"] for r in all_runs}),
                "stable": len(all_runs) >= 3 and len({r["fingerprint"] for r in all_runs}) == 1,
            },
        }

    def resolve(self, run_id):
        with self.lock:
            row = self.db.execute("SELECT detail FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row or json.loads(row["detail"])["result"]["terminal_state"] != "escalated":
                return False
            self.db.execute("UPDATE runs SET resolved=1 WHERE run_id=?", (run_id,))
            self.db.commit()
            return True
