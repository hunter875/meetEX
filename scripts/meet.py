"""Cross-platform local operations. Run from any working directory; no paid calls."""

import argparse
import importlib.util
import json
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NPM = "npm.cmd" if os.name == "nt" else "npm"
sys.path.insert(0, str(ROOT / "backend"))
QUALITY_FILES = [
    "backend/app/main.py",
    "backend/app/config.py",
    "backend/app/storage.py",
    "backend/app/ownership.py",
    "backend/app/report_export.py",
    "backend/app/migration.py",
    "backend/app/backup.py",
    "backend/app/runner.py",
    "backend/app/version.py",
    "backend/tests/test_phase5_operations.py",
    "scripts/meet.py",
    "scripts/package_local.py",
    "scripts/soak_phase5.py",
    "scripts/ci_check.py",
    "scripts/diagnostics.py",
    "scripts/clean_phase5.py",
    "scripts/review_phase5.py",
    "scripts/check_phase5_docs.py",
    "scripts/load_demo.py",
]


def run(arguments, **kwargs):
    subprocess.run([str(x) for x in arguments], cwd=ROOT, check=True, **kwargs)


def request(path, *, directory=None, body=None, method=None):
    headers = {"Content-Type": "application/json"}
    if directory:
        headers["Authorization"] = (
            "Bearer " + (directory / "pairing-token").read_text("utf8").strip()
        )
    call = urllib.request.Request(
        "http://127.0.0.1:8765" + path,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(call, timeout=5) as response:
        return json.load(response)


def ready():
    try:
        return request("/ready")
    except (OSError, ValueError):
        return None


def verify_instance(directory):
    status = ready()
    identity = json.loads((directory / "runtime.json").read_text("utf8"))
    if not status or status.get("instance") != identity.get("instance"):
        raise RuntimeError(
            "PROCESS_UNVERIFIED: port does not match this data directory; no process was stopped."
        )
    return identity


def setup(semantic=False):
    if sys.version_info < (3, 11):
        raise RuntimeError("Install official Python 3.11+ with FTS5 (validated on Python 3.13).")
    if not shutil.which("node") or not shutil.which(NPM):
        raise RuntimeError("Install Node 22.12+ and npm, then rerun setup.")
    version = subprocess.check_output(["node", "--version"], text=True).strip().lstrip("v")
    if tuple(map(int, version.split(".")[:2])) < (22, 12):
        raise RuntimeError("Node 22.12+ required.")
    if not PYTHON.exists():
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    run([PYTHON, "-m", "pip", "install", "-r", ROOT / "backend/requirements.lock"])
    run([PYTHON, "-m", "pip", "install", "-r", ROOT / "backend/requirements-dev.lock"])
    if semantic:
        run(
            [
                PYTHON,
                "-m",
                "pip",
                "install",
                "-r",
                ROOT / "backend/requirements-semantic.lock",
                "--extra-index-url",
                "https://download.pytorch.org/whl/cpu",
            ]
        )
    run([NPM, "ci", "--no-audit", "--no-fund"])
    run(
        [
            PYTHON,
            "-c",
            "import sqlite3; from zoneinfo import ZoneInfo; sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE t USING fts5(text)'); ZoneInfo('America/Los_Angeles')",
        ]
    )
    print("Setup complete. Next: python scripts/meet.py build")


def doctor(directory):
    from app.backup import readonly
    from app.ownership import schema_version
    from app.version import APP_VERSION, PROTOCOL_VERSION, SCHEMA_VERSION
    from contextlib import closing

    checks = []

    def add(name, status, action):
        checks.append(dict(check=name, status=status, action=action))

    add(
        "runtime",
        "PASS",
        f"Python {platform.python_version()}; Node "
        + subprocess.check_output(["node", "--version"], text=True).strip(),
    )
    missing = [
        name
        for name in ("fastapi", "uvicorn", "httpx", "dotenv")
        if importlib.util.find_spec(name) is None
    ]
    add(
        "dependencies",
        "FAIL" if missing else "PASS",
        "Run setup" if missing else "Required modules available",
    )
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        add("fts5", "PASS", sqlite3.sqlite_version)
    except sqlite3.Error:
        add("fts5", "FAIL", "Install official Python with SQLite FTS5")
    # Probe only a disposable file; never acquire/delete the app lock or open DB read-write.
    try:
        ancestor = directory
        while not ancestor.exists():
            ancestor = ancestor.parent
        with tempfile.TemporaryFile(dir=ancestor) as probe:
            probe.write(b"write-probe")
            probe.flush()
        add(
            "data_permissions",
            "PASS" if ancestor == directory else "WARN",
            "Writable"
            if ancestor == directory
            else "Data directory not created yet; start initializes it",
        )
    except OSError:
        add(
            "data_permissions", "FAIL", "Choose a writable --data-dir owned by your Windows account"
        )
    if (directory / "copilot.sqlite3").exists():
        try:
            with closing(readonly(directory / "copilot.sqlite3")) as db:
                version = schema_version(db)
            add(
                "schema",
                "FAIL" if version > SCHEMA_VERSION else "PASS",
                f"Database {version}; app supports <= {SCHEMA_VERSION}; use matching source if newer",
            )
        except sqlite3.Error:
            add("schema", "FAIL", "Cannot read database; stop backend and validate a backup")
    else:
        add("schema", "WARN", "No local database yet; run start")
    status = ready()
    if not status:
        with socket.socket() as probe:
            occupied = probe.connect_ex(("127.0.0.1", 8765)) == 0
        add(
            "backend",
            "FAIL" if occupied else "WARN",
            "Port 8765 occupied by unverified app; stop it yourself or choose another session"
            if occupied
            else "Backend not running; run start",
        )
    else:
        add(
            "backend",
            "PASS" if status.get("ready") else "FAIL",
            "Ready" if status.get("ready") else "Starting/stopping; inspect local startup error",
        )
        add(
            "compatibility",
            "PASS"
            if status.get("protocol_version") == PROTOCOL_VERSION
            and status.get("app_version") == APP_VERSION
            else "FAIL",
            "Update backend and extension together; reload unpacked extension",
        )
        try:
            verify_instance(directory)
            request("/api/v1/settings", directory=directory)
            add("pairing", "PASS", "Local credential accepted; extension must use the same token")
        except (OSError, ValueError, RuntimeError):
            add("pairing", "FAIL", "Token/instance mismatch; verify --data-dir, then pair again")
    extension_id = os.getenv("MEET_EXTENSION_ID", "")
    import re

    add(
        "extension_origin",
        "PASS" if re.fullmatch("[a-p]{32}", extension_id) else "WARN",
        "Exact extension ID configured"
        if re.fullmatch("[a-p]{32}", extension_id)
        else "Run pair-extension.ps1 -ExtensionId ID, restart backend",
    )
    add(
        "semantic",
        "INFO",
        (
            "Dependency installed; model load remains explicit"
            if importlib.util.find_spec("sentence_transformers")
            else "Optional E5 absent; keyword FTS5 remains supported"
        ),
    )
    return dict(
        app_version=APP_VERSION, protocol_version=PROTOCOL_VERSION, checks=checks, paid_calls=0
    )


def test(browser=False):
    evidence = ROOT / ".local/checks"
    evidence.mkdir(parents=True, exist_ok=True)
    run([PYTHON, "-m", "pytest", "-q", "--junitxml=" + str(evidence / "backend.xml")])
    run(
        [NPM, "test"],
        env={**os.environ, "MEET_FRONTEND_RESULTS_FILE": str(evidence / "frontend.json")},
    )
    run([NPM, "run", "typecheck"])
    run([NPM, "run", "build"])
    run([NPM, "run", "contracts"])
    run([PYTHON, "-m", "ruff", "check", "backend", *QUALITY_FILES])
    run([PYTHON, "-m", "ruff", "check", "--select", "E4,E7,E9,F", *QUALITY_FILES])
    run([PYTHON, "-m", "ruff", "format", "--check", *QUALITY_FILES])
    run([NPM, "run", "format:check"])
    # Original Phase 1 semantic probes and Phase 2-4 regressions are included in pytest/vitest/E2E.
    if browser:
        run(["npx.cmd" if os.name == "nt" else "npx", "playwright", "install", "chromium"])
        environment = {
            **os.environ,
            "MEET_E2E_RESULTS_FILE": str(evidence / "browser.json"),
            "MEET_E2E_EVIDENCE_DIR": str(evidence / "browser"),
        }
        run([NPM, "run", "test:e2e"], env=environment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "setup",
            "build",
            "start",
            "stop",
            "doctor",
            "test",
            "backup",
            "restore",
            "rotate-token",
            "update",
            "package",
            "demo",
        ],
    )
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--path", type=Path, help="Backup destination / restore source / artifact output"
    )
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    if args.command == "setup":
        setup(args.semantic)
        return
    if not PYTHON.exists():
        raise RuntimeError("DEPENDENCIES_MISSING: run python scripts/meet.py setup first.")
    # POSIX venv executables are often symlinks to the base interpreter. Compare
    # prefixes, otherwise a global interpreter looks like the venv executable.
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        result = subprocess.run(
            [str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=Path.cwd()
        )
        raise SystemExit(result.returncode)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from app.config import data_directory

    directory = data_directory(args.data_dir)
    os.environ["MEET_DATA_DIR"] = str(directory)
    if args.command == "build":
        run([NPM, "run", "build"])
    elif args.command == "demo":
        run([PYTHON, ROOT / "scripts/load_demo.py"])
    elif args.command == "test":
        try:
            test(args.browser)
        finally:
            from diagnostics import sanitize

            sanitize()
    elif args.command == "start":
        # Foreground server owns the OS lock; port conflict is checked before any DB changes.
        run([PYTHON, "-m", "app.runner"], env={**os.environ, "PYTHONPATH": str(ROOT / "backend")})
    elif args.command == "stop":
        identity = verify_instance(directory)
        request(
            "/api/v1/local/shutdown", directory=directory, body={"instance": identity["instance"]}
        )
        deadline = time.monotonic() + 40
        from app.ownership import DataOwnership

        while time.monotonic() < deadline:
            try:
                with DataOwnership(directory):
                    print("Stopped; data ownership released.")
                    return
            except RuntimeError:
                time.sleep(0.1)
        raise RuntimeError(
            "STOP_TIMEOUT: shutdown requested but writer still active; inspect log; no PID was killed."
        )
    elif args.command == "doctor":
        result = doctor(directory)
        print(json.dumps(result, indent=2))
        if any(c["status"] == "FAIL" for c in result["checks"]):
            raise SystemExit(1)
    elif args.command in ("backup", "restore"):
        if not args.path:
            parser.error("--path required")
        from app.backup import backup, restore

        result = (backup if args.command == "backup" else restore)(directory, args.path.resolve())
        print(json.dumps(result, indent=2))
    elif args.command == "rotate-token":
        from app.ownership import DataOwnership, atomic_private

        if ready():
            verify_instance(directory)
            result = request("/api/v1/local/pairing/rotate", directory=directory, body={})
        else:
            import secrets

            with DataOwnership(directory):
                atomic_private(directory / "pairing-token", secrets.token_urlsafe(32))
            result = dict(rotated=True, re_pair=True)
        print(json.dumps(result))
    elif args.command == "update":
        if not args.path:
            parser.error(
                "update requires --path NEW_PRE_UPGRADE_BACKUP_DIRECTORY; select target source first"
            )
        from app.backup import backup, inspect_database
        from app.ownership import DataOwnership
        from app.storage import Storage

        with DataOwnership(directory):
            backup(directory, args.path.resolve())
            setup(args.semantic)
            run([NPM, "run", "build"])
            db = Storage.connect(str(directory / "copilot.sqlite3"))
            db.close()
            inspect_database(directory / "copilot.sqlite3")
        print("Updated; backup retained. Start backend, reload unpacked extension and run doctor.")
    elif args.command == "package":
        run(
            [
                PYTHON,
                ROOT / "scripts/package_local.py",
                "--output",
                args.path or ROOT / ".local/artifacts",
            ]
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (
        RuntimeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
        ImportError,
        sqlite3.Error,
    ) as error:
        # Do not print exception body: HTTP/validation/provider errors may contain sensitive input.
        message = (
            str(error)
            if isinstance(error, RuntimeError)
            else type(error).__name__
            + ": operation failed; run doctor / inspect local startup output."
        )
        print(message, file=sys.stderr)
        raise SystemExit(1)
