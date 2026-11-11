"""Offline end-to-end regression command, including the unchanged supplied runner."""

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    env = {**os.environ, "GEMINI_ENABLED": "false"}

    def command(*args):
        subprocess.run(args, env=env, check=True)

    command(sys.executable, "-m", "pytest", "-q")
    command(sys.executable, "-m", "ruff", "check", ".")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)
    with tempfile.TemporaryDirectory() as temporary:
        env["UI_DB_PATH"] = str(Path(temporary) / "history.sqlite3")
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8011"], env=env
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Regression API failed to start")
                try:
                    urllib.request.urlopen("http://127.0.0.1:8011/health", timeout=1)
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Regression API did not become healthy")
            for directory in ["conversations", "adversarial"]:
                command(
                    sys.executable,
                    "runner.py",
                    "--url",
                    "http://127.0.0.1:8011/agent/run",
                    "--dir",
                    directory,
                    "--repeat",
                    "3",
                    "--out",
                    f"results/offline-{directory}",
                )
                command(
                    sys.executable,
                    "scripts/compare_results.py",
                    "--dir",
                    directory,
                    "--out",
                    f"results/offline-{directory}",
                    "--report",
                    f"evidence/offline-{directory}.json",
                )
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
