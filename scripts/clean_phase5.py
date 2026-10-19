"""Clean clone on the existing developer host: setup, real runner/demo, recovery,
update and the complete published test command. No existing venv/node/data reused.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    clean = (args.destination or ROOT / ".local" / ("Phase 5 clean " + commit[:12])).resolve()
    if clean.exists():
        raise SystemExit("Choose a new clean destination; no existing directory is removed.")
    evidence = ROOT / "docs/evidence/phase5"
    evidence.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "DEEPSEEK_API_KEY": "",
        "MEET_EXTENSION_ID": "a" * 32,
        "MEET_DEV_ORIGIN": "",
        "PYTHONIOENCODING": "utf8",
    }
    environment.pop("PYTHONPATH", None)
    environment.pop("VIRTUAL_ENV", None)
    data = clean / ".local" / "runtime data"
    environment["MEET_DATA_DIR"] = str(data)
    python = clean / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    entry = clean / "scripts/meet.py"
    record = dict(
        status="RUNNING",
        source_commit=commit,
        scope="Clean local clone on existing Windows developer account/runtime; NOT independent clean Windows",
        shared_caches="pip/npm/Playwright download caches may be reused; no venv/node_modules/data/browser profile copied",
        initial=dict(venv=False, node_modules=False, data=False),
        steps=[],
        paid_calls=0,
    )

    def save():
        (evidence / "clean-setup.json").write_text(json.dumps(record, indent=2), encoding="utf8")

    def run(name, command, timeout=900):
        started = time.monotonic()
        with (evidence / ("clean-" + name + ".log")).open("wb") as log:
            result = subprocess.run(
                [str(x) for x in command],
                cwd=clean if clean.exists() else ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        record["steps"].append(
            dict(
                name=name,
                exit_code=result.returncode,
                duration_s=round(time.monotonic() - started, 2),
            )
        )
        save()
        if result.returncode:
            raise RuntimeError("Clean step failed: " + name)

    def api(path, method="GET", body=None, credential=None):
        secret = credential or (data / "pairing-token").read_text("utf8").strip()
        request = urllib.request.Request(
            "http://127.0.0.1:8765" + path,
            method=method,
            headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"},
            data=json.dumps(body).encode() if body is not None else None,
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    process = None
    log = None

    def start():
        nonlocal process, log
        log = (evidence / "clean-runner.log").open("ab")
        process = subprocess.Popen(
            [str(python), "-m", "app.runner"],
            cwd=clean,
            env={**environment, "PYTHONPATH": str(clean / "backend")},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Clean backend exited before readiness")
            try:
                if api("/ready")["ready"]:
                    return
            except (OSError, ValueError):
                time.sleep(0.1)
        raise RuntimeError("Clean backend not ready")

    def stop():
        nonlocal process, log
        if process and process.poll() is None:
            run("stop", [python, entry, "stop"], 50)
            process.wait(timeout=10)
            assert process.returncode == 0
        if log:
            log.close()
            log = None

    def fingerprint():
        with closing(
            sqlite3.connect((data / "copilot.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as db:
            names = [
                r[0]
                for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'chunks_fts%'"
                )
            ]
            rows = {
                name: sorted(
                    json.dumps(tuple(row), sort_keys=True)
                    for row in db.execute(f"SELECT * FROM {name}")
                )
                for name in names
            }
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

    try:
        run(
            "clone",
            [
                "git",
                "clone",
                "--no-hardlinks",
                "--branch",
                "codex/phase5-local-operations",
                ROOT,
                clean,
            ],
        )
        assert (
            not (clean / ".venv").exists()
            and not (clean / "node_modules").exists()
            and not data.exists()
        )
        base_python = getattr(sys, "_base_executable", sys.executable)
        run("setup", [base_python, entry, "setup"])
        run("build", [python, entry, "build"])
        start()
        status = api("/ready")
        assert (
            status["ready"]
            and status["schema_version"] == 2
            and status["protocol_version"] == 1
            and not status["provider_key"]
        )
        run("doctor", [python, entry, "doctor"])
        run("demo", [python, entry, "demo"])
        project = next(p for p in api("/api/v1/projects") if p["name"].startswith("DEMO"))
        assert len(api(f"/api/v1/projects/{project['id']}/sources")) == 12
        meeting = api(
            "/api/v1/meetings",
            "POST",
            dict(project_id=project["id"], title="SYNTHETIC CLEAN", demo=True, timezone="UTC"),
        )
        mid = meeting["id"]
        api(f"/api/v1/meetings/{mid}", "PATCH", dict(auto_mode=False, self_speaker="Minh"))
        for seq, text in enumerate(
            ["Confirmed: test API-17 in staging.", "I will review API-71 by tomorrow."], 1
        ):
            api(
                f"/api/v1/meetings/{mid}/demo-caption",
                "POST",
                dict(
                    type="caption.upsert",
                    protocol_version=1,
                    event_id=f"clean-{seq}",
                    capture_epoch="clean",
                    segment_id=f"clean-{seq}",
                    revision=1,
                    seq=seq,
                    speaker_label="Minh" if seq == 2 else "Client",
                    text=text,
                    observed_at="2026-10-19T14:00:00Z",
                    stable=True,
                    adapter_version="synthetic-clean",
                ),
            )
        api(f"/api/v1/meetings/{mid}/suggest", "POST", dict(action="suggest"))
        time.sleep(0.3)
        api(
            f"/api/v1/meetings/{mid}/control",
            "POST",
            dict(action="end", idempotency_key="clean-end"),
        )
        revision = api(f"/api/v1/meetings/{mid}")["transcript_revision"]
        job = api(f"/api/v1/meetings/{mid}/reports", "POST", dict(transcript_revision=revision))
        for _ in range(100):
            final = api("/api/v1/jobs/" + job["id"])
            if final["status"] in ("ready", "error"):
                break
            time.sleep(0.05)
        assert final["status"] == "ready"
        report = api("/api/v1/reports/" + final["report_id"])
        saved = api(
            "/api/v1/reports/" + report["id"],
            "PATCH",
            dict(
                expected_version=report["version"],
                payload={**report["payload"], "summary_vi": "SYNTHETIC CLEAN USER EDIT"},
                reviewed=True,
            ),
        )
        assert (
            saved["version"] == 2
            and api("/api/v1/reports/" + saved["id"] + "/export?format=json")["payload"][
                "summary_vi"
            ]
            == "SYNTHETIC CLEAN USER EDIT"
        )
        old_token = (data / "pairing-token").read_text().strip()
        run("rotate", [python, entry, "rotate-token"])
        try:
            api("/api/v1/projects", credential=old_token)
            raise AssertionError("Old token accepted")
        except urllib.error.HTTPError as error:
            assert error.code == 401
        assert api("/api/v1/projects")
        expected = fingerprint()
        destination = clean / ".local" / "online backup"
        run("backup", [python, entry, "backup", "--path", destination])
        api(
            "/api/v1/projects/" + project["id"],
            "PATCH",
            dict(name="SYNTHETIC MUTATED AFTER BACKUP"),
        )
        stop()
        run("restore", [python, entry, "restore", "--path", destination])
        assert fingerprint() == expected
        start()
        assert (
            api("/api/v1/reports/" + saved["id"])["payload"]["summary_vi"]
            == "SYNTHETIC CLEAN USER EDIT"
        )
        stop()
        run("update", [python, entry, "update", "--path", clean / ".local" / "pre update backup"])
        assert fingerprint() == expected
        start()
        run("doctor-after-update", [python, entry, "doctor"])
        stop()
        # Actual MV3 pair/demo/edit/export/recovery and all regression suites in a fresh dependency tree.
        run("checks", [python, clean / "scripts/ci_check.py"], 900)
        record.update(
            status="PASS",
            application_rows_preserved=True,
            report_user_edit_preserved=True,
            upgrade="schema2-to2 update/reinstall; schema1-to2 validated by operations suite",
            online_wal_restore=True,
            token_rotation=True,
            actual_mv3_pair="PASS in seven browser E2E",
            independent_windows="NOT TESTED",
        )
    except Exception as error:
        record.update(status="FAIL", failure_type=type(error).__name__, failure=str(error)[:160])
        raise
    finally:
        try:
            stop()
        finally:
            save()
    print(json.dumps(record))


if __name__ == "__main__":
    main()
