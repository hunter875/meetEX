"""Redact synthetic pairing values before printing/exporting test diagnostics."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def redact(text):
    text = re.sub(r"Bearer\s+[A-Za-z0-9_-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?<![\w-])[A-Za-z0-9_-]{43}(?![\w-])", "[REDACTED_OPAQUE_VALUE]", text)
    return re.sub(r"\bsk-[A-Za-z0-9_-]{20,}", "[REDACTED_KEY]", text)


def sanitize():
    for directory in (ROOT / ".local/checks", ROOT / "test-results"):
        if not directory.exists():
            continue
        for file in directory.rglob("*"):
            if not file.is_file():
                continue
            if file.suffix in (".zip", ".har", ".webm"):
                # Browser traces/HARs can embed request credentials; never publish them.
                file.unlink()
            elif file.suffix in (".json", ".log", ".xml", ".txt", ".md", ".html"):
                original = file.read_text("utf8")
                safe = redact(original)
                if safe != original:
                    file.write_text(safe, encoding="utf8")


if __name__ == "__main__":
    sanitize()
