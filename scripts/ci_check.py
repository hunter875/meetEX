"""Run the published checks with redacted console and failure artifacts."""

import subprocess
import sys
import os
from pathlib import Path

from diagnostics import redact, sanitize


def main():
    sys.stdout.reconfigure(encoding="utf8", errors="replace")
    os.environ["PYTHONIOENCODING"] = "utf8"
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [sys.executable, str(root / "scripts/meet.py"), "test", "--browser"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf8",
        errors="replace",
    )
    try:
        for line in process.stdout:
            print(redact(line), end="", flush=True)
        return process.wait()
    finally:
        sanitize()


if __name__ == "__main__":
    raise SystemExit(main())
