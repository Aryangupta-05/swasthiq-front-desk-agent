"""One SQLite connection per schedule. An evaluation owns a private snapshot.

BEGIN IMMEDIATE + overlap triggers serialize competing writers even on independent
connections to the same file. Constraints apply to both doctors and patients.
"""

import json
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_clinic():
    return json.loads((ROOT / "clinic.json").read_text(encoding="utf-8"))


class Schedule:
    def __init__(self, path=":memory:", clinic=None):
        self.clinic = clinic if clinic is not None else load_clinic()
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS appointments(
          id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, doctor_id TEXT NOT NULL,
          date TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('booked','cancelled')),
          CHECK(start < end));
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS no_overlap_insert BEFORE INSERT ON appointments
        WHEN NEW.status='booked' AND EXISTS (
          SELECT 1 FROM appointments a WHERE a.status='booked' AND a.date=NEW.date
          AND (a.doctor_id=NEW.doctor_id OR a.patient_id=NEW.patient_id)
          AND a.start < NEW.end AND a.end > NEW.start)
        BEGIN SELECT RAISE(ABORT, 'slot conflict: doctor or patient already booked'); END;
        CREATE TRIGGER IF NOT EXISTS no_overlap_update BEFORE UPDATE ON appointments
        WHEN NEW.status='booked' AND EXISTS (
          SELECT 1 FROM appointments a WHERE a.id<>NEW.id AND a.status='booked' AND a.date=NEW.date
          AND (a.doctor_id=NEW.doctor_id OR a.patient_id=NEW.patient_id)
          AND a.start < NEW.end AND a.end > NEW.start)
        BEGIN SELECT RAISE(ABORT, 'slot conflict: doctor or patient already booked'); END;
        """)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if not self.db.execute("SELECT 1 FROM metadata WHERE key='seeded'").fetchone():
                    self.db.executemany(
                        "INSERT INTO appointments VALUES(:id,:patient_id,:doctor_id,:date,:start,:end,:status)",
                        self.clinic["appointments"],
                    )
                    self.db.execute("INSERT INTO metadata VALUES('seeded','1')")
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def appointments(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM appointments ORDER BY id")]

    def close(self):
        self.db.close()
