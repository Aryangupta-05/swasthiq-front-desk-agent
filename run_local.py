"""One-command host launcher: python run_local.py (Python 3.11+, Node 24+)."""

import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    os.chdir(ROOT)
    if not shutil.which("npm.cmd" if os.name == "nt" else "npm"):
        raise SystemExit("Install Node.js 24 or newer, then rerun python run_local.py")
    packages = {
        line.split("==")[0]: line.split("==")[1]
        for line in (ROOT / "requirements.txt").read_text().splitlines()
        if "==" in line
    }
    missing = False
    for name, version in packages.items():
        try:
            missing = missing or importlib.metadata.version(name) != version
        except importlib.metadata.PackageNotFoundError:
            missing = True
    if missing:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    if not (ROOT / "frontend" / "node_modules").exists():
        subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)
    print("\nOpen http://127.0.0.1:8000 · Ctrl+C stops the server\n", flush=True)
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8000"], check=True
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
