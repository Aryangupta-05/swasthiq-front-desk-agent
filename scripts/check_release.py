"""Scan the exact Git file set before publication; never print a credential."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    names = [n for n in names if n]
    forbidden = [
        n
        for n in names
        if Path(n).suffix.lower() in [".pdf", ".zip", ".sqlite3"]
        or n == ".env"
        or n.startswith(("private/", "frontend/node_modules/", ".venv/"))
    ]
    secrets = []
    for name in names:
        raw = (ROOT / name).read_bytes()
        if re.search(
            rb"AIza[0-9A-Za-z_\-]{30,}|gh[pousr]_[0-9A-Za-z]{30,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----", raw
        ):
            secrets.append(name)
    assert not forbidden, f"Forbidden publication files: {forbidden}"
    assert not secrets, f"Possible credentials in: {secrets}"
    assert len(list((ROOT / "adversarial").glob("*.json"))) == 8
    assert len(list((ROOT / "conversations").glob("*.json"))) == 15
    print(f"Release scan passed: {len(names)} tracked files; no credentials or confidential input documents")


if __name__ == "__main__":
    main()
