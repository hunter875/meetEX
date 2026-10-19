"""Validate current evidence and preserve historical Phase 1-4 reports/specs."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/evidence/phase5/documentation-qa.json")
    args = parser.parse_args()
    output = ROOT / args.output
    review = json.loads((ROOT / "docs/evidence/phase5/review.json").read_text("utf8"))
    assert review["result"].startswith("PARTIAL") and review["paid_provider_calls"] == 0
    assert (
        review["release_gates"]["independent_clean_windows"]
        == review["release_gates"]["live_meet"]
        == "NOT TESTED"
    )
    for name, expected in review["source_hashes"].items():
        assert hashlib.sha256((ROOT / name).read_text("utf8").encode()).hexdigest() == expected, (
            name
        )
    files = [
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "docs/spec").glob("*.md")),
    ]
    for file in files:
        for link in re.findall(r"\]\(([^)]+)\)", file.read_text("utf8")):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("#"):
                continue
            target = (file.parent / link.split("#")[0]).resolve()
            assert target.exists() or target == output.resolve(), f"{file.name}: {link}"
    protected = [
        "docs/spec",
        *[f"docs/evidence/phase{n}" for n in range(1, 5)],
        *[f"docs/PHASE{n}_REPORT.md" for n in range(1, 5)],
    ]
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", review["base_commit"], "--", *protected], cwd=ROOT, text=True
    ).strip()
    assert not changed, "Historical evidence/spec/report changed: " + changed
    report = (ROOT / "docs/PHASE5_REPORT.md").read_text("utf8")
    assert "NOT TESTED" in report and "PHASE3_REPORT.md" in report
    result = dict(
        status="PASS",
        historical_evidence_unchanged=True,
        links_valid=True,
        source_hashes_valid=True,
        paid_calls=0,
        release_ready=False,
        independent_windows="NOT TESTED",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
