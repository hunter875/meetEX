"""Assemble measured Phase 5 status without upgrading untested release gates."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/phase5"


def read(name):
    return json.loads((EVIDENCE / name).read_text("utf8"))


def main():
    suites = list(ET.parse(EVIDENCE / "backend-final.xml").getroot().iter("testsuite"))
    assert suites and all(
        int(s.get("failures", 0)) == int(s.get("errors", 0)) == int(s.get("skipped", 0)) == 0
        for s in suites
    )
    frontend = read("frontend-final.json")
    browser = read("browser-final-results.json")
    assert frontend["numFailedTests"] == frontend["numPendingTests"] == 0
    assert (
        browser["stats"]["unexpected"] == browser["stats"]["skipped"] == 0
        and browser["stats"]["expected"] == 7
    )
    semantic = read("semantic-regression.json")
    assert semantic["result"] == "PASS" and all(
        probe["blocked"] for probe in semantic["original_probes"]
    )
    assert all(g["false_accepts"] == g["false_rejects"] == 0 for g in semantic["groups"].values())
    memory = read("memory-regression.json")
    assert memory["totals"]["correct_items"] == memory["totals"]["expected_items"] == 38
    assert (
        memory["totals"]["wrong_items"]
        == memory["totals"]["missing_items"]
        == memory["totals"]["extra_items"]
        == 0
    )
    clean = (
        read("clean-setup.json")
        if (EVIDENCE / "clean-setup.json").exists()
        else {"status": "NOT TESTED"}
    )
    soak = (
        read("soak-final-60m.json")
        if (EVIDENCE / "soak-final-60m.json").exists()
        else {"status": "NOT TESTED"}
    )
    artifact = (
        read("artifact-manifest.json") if (EVIDENCE / "artifact-manifest.json").exists() else None
    )
    ci = (
        read("ci-result.json")
        if (EVIDENCE / "ci-result.json").exists()
        else {"status": "NOT TESTED"}
    )
    quality = read("quality.json")
    assert quality["status"] == "PASS"
    paths = [
        *sorted((ROOT / "backend/app").rglob("*.py")),
        *sorted((ROOT / "extension/src").rglob("*.ts")),
        *sorted((ROOT / "extension/src").rglob("*.tsx")),
        ROOT / "scripts/meet.py",
        ROOT / "scripts/package_local.py",
        ROOT / "scripts/soak_phase5.py",
        ROOT / "backend/requirements.lock",
        ROOT / "backend/requirements-dev.lock",
        ROOT / "package-lock.json",
        ROOT / ".github/workflows/checks.yml",
    ]
    record = dict(
        result="PARTIAL: internal release candidate; independent/live gates remain open",
        date="2026-10-19",
        base_commit="9a5ac7153343a4b84256fbc1343267eeb285de55",
        source_commit_at_review=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        app_version="0.1.0",
        protocol_version=1,
        schema_version=2,
        paid_provider_calls=0,
        regression=dict(
            backend=sum(int(s.get("tests", 0)) for s in suites),
            frontend=frontend["numPassedTests"],
            browser=7,
            semantic=semantic["result"],
            memory=memory["totals"],
        ),
        areas=dict(
            A="PASS bounded refactor/quality scope",
            B="PASS tested Windows operations",
            C="PASS schema1-to2 and schema2 recovery paths",
            D="PASS automated REST/WS/MV3",
            E="PASS tested scope" if ci.get("status") == "PASS" and artifact else "PARTIAL",
            F="PASS controlled developer-host scope"
            if clean.get("status") == soak.get("status") == "PASS"
            else "PARTIAL",
        ),
        clean_setup=clean,
        soak=dict(
            status=soak["status"],
            elapsed_s=soak.get("elapsed_s"),
            planned_seconds=soak.get("plan", {}).get("seconds"),
            captions=soak.get("captions"),
            reports=soak.get("reports"),
            attempts=soak.get("provider_attempts"),
            ack=soak.get("ack"),
        ),
        ci=ci,
        artifact=artifact,
        release_gates=dict(
            core_correctness="PARTIAL outside bounded grammar",
            live_meet="NOT TESTED",
            current_real_provider_quality="NOT TESTED",
            long_report="PARTIAL controlled only",
            performance_cost="PARTIAL; no end-to-end SLA/real token cost",
            upgrade_recovery="PASS tested paths",
            independent_clean_windows="NOT TESTED",
            operational_soak=soak["status"],
            semantic_profile="NOT TESTED in Phase 5",
        ),
        hash_format="utf8-lf",
        source_hashes={
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_text("utf8").encode()).hexdigest()
            for p in paths
        },
    )
    (EVIDENCE / "review.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    print(
        json.dumps(
            {k: record[k] for k in ("result", "regression", "areas", "release_gates")},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
