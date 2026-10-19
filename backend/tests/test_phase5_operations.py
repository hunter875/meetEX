"""Operational invariants on disposable data; no network provider or personal DB."""

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.backup import backup, restore, validate_backup
from app.config import Config
from app.ingestion import Ingestion
from app.main import create_app
from app.migration import migrate
from app.ownership import DataOwnership, atomic_private
from app.retrieval import Semantic
from app.storage import Storage, dumps, now, uid
from app.llm import ReportPayload
from .conftest import caption

ROOT = Path(__file__).resolve().parents[2]


def seed(directory, *, memory=False):
    store = Storage(directory)
    project = store.create_project(
        dict(name="Upgrade synthetic", description="Keep description", glossary={"API": "endpoint"})
    )
    ingestion = Ingestion(store, Semantic(directory / "models"))
    source = ingestion.add(
        project["id"],
        dict(kind="text", title="Upgrade source", pasted_text="API-17 staging tests remain open."),
    )
    ingestion.sync(source["id"])
    meeting = store.create_meeting(
        dict(
            project_id=project["id"],
            title="Upgrade meeting",
            timezone="UTC",
            persistence_mode="memory" if memory else "local",
            demo=True,
        )
    )
    store.apply_caption(
        meeting["id"], caption("I will review API-17.", segment="upgrade", revision=1, seq=1)
    )
    store.apply_caption(
        meeting["id"],
        caption("I will review API-17 by 2026-10-25.", segment="upgrade", revision=2, seq=2),
    )
    parent = None
    for version in (1, 2):
        report = dict(
            id=uid(),
            meeting_id=meeting["id"],
            version=version,
            user_edits=version == 2,
            payload=ReportPayload(
                summary_vi="User saved edit" if version == 2 else "Draft"
            ).model_dump(),
            transcript_revision=2,
            mode="demo",
            created_at=now(),
            reviewed_at=now() if version == 2 else None,
            parent_id=parent,
        )
        with store.db_for(meeting["id"]):
            store.db_for(meeting["id"]).execute(
                "INSERT INTO reports VALUES(?,?,?,?)",
                (report["id"], meeting["id"], version, dumps(report)),
            )
        parent = report["id"]
    store.control(meeting["id"], dict(action="end", idempotency_key=uid()))
    return store, project, meeting


def content(db):
    # Ignore SQLite page/WAL bytes; compare every application row and FK/index behavior.
    names = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'chunks_fts%' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {
        name: sorted(tuple(row) for row in db.execute(f"SELECT * FROM {name}")) for name in names
    }


def test_import_schema_has_no_data_or_environment_side_effect(tmp_path):
    directory = tmp_path / "must not exist"
    code = "import os; before=dict(os.environ); from app.main import app; assert app.openapi(); assert before==dict(os.environ)"
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "backend"), "MEET_DATA_DIR": str(directory)},
    )
    assert not directory.exists()


def test_os_lock_ignores_stale_pid_and_rejects_other_process(tmp_path):
    (tmp_path / "runtime.json").write_text('{"pid":1,"instance":"stale"}')
    with DataOwnership(tmp_path):
        code = 'from app.ownership import DataOwnership; import sys; DataOwnership(__import__("pathlib").Path(sys.argv[1])).acquire()'
        result = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)],
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
        )
        assert result.returncode != 0 and b"DATA_BUSY" in result.stderr
    with DataOwnership(tmp_path):
        pass


def test_two_asgi_apps_cannot_own_same_data(tmp_path):
    config = Config(tmp_path, "FAKE_PAIR", ())
    with TestClient(create_app(config), base_url="http://127.0.0.1:8765"):
        with pytest.raises(RuntimeError, match="DATA_BUSY"):
            with TestClient(create_app(config)):
                pass
    with DataOwnership(tmp_path):
        pass


def test_start_failure_releases_os_lock_and_never_ready(tmp_path):
    app = create_app(Config(tmp_path, "FAKE_PAIR", ()))
    with patch("app.main.Storage", side_effect=RuntimeError("synthetic disk permission failure")):
        with pytest.raises(RuntimeError):
            with TestClient(app):
                pass
    assert not app.state.ready and not (tmp_path / "runtime.json").exists()
    with DataOwnership(tmp_path):
        pass


def test_future_schema_rejected_before_wal_or_data_changes(tmp_path):
    path = tmp_path / "future.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.executescript(
            "CREATE TABLE schema_version(version INTEGER PRIMARY KEY); INSERT INTO schema_version VALUES(99);"
        )
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="SCHEMA_NEWER"):
        Storage.connect(str(path))
    assert path.read_bytes() == before and not Path(str(path) + "-wal").exists()


def test_migration_failure_rolls_back_and_history_gaps_rejected(tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "001.sql").write_text((ROOT / "backend/app/migrations/001.sql").read_text("utf8"))
    (directory / "002.sql").write_text(
        "CREATE TABLE should_rollback(x); INSERT INTO missing_table VALUES(1);"
    )
    with closing(sqlite3.connect(":memory:")) as db:
        with pytest.raises(sqlite3.Error):
            migrate(db, directory)
        assert [r[0] for r in db.execute("SELECT version FROM schema_version")] == [1]
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='should_rollback'").fetchone()
        db.execute("DELETE FROM schema_version")
        db.execute("INSERT INTO schema_version VALUES(2)")
        with pytest.raises(RuntimeError, match="MIGRATION_HISTORY"):
            migrate(db)


def test_v1_full_fixture_upgrade_preserves_rows_and_fts(tmp_path):
    source = tmp_path / "source"
    store, project, meeting = seed(source)
    expected = content(store.disk)
    store.close()
    # Materialize a genuine schema-1 database with all original schema-1 tables/data.
    path = tmp_path / "v1.sqlite3"
    with closing(sqlite3.connect(path)) as old:
        old.executescript((ROOT / "backend/app/migrations/001.sql").read_text("utf8"))
        for name, rows in expected.items():
            if name in ("schema_version", "segment_revisions", "memory_items", "memory_versions"):
                continue
            for row in rows:
                old.execute(f"INSERT INTO {name} VALUES({','.join('?' for _ in row)})", row)
        old.commit()
    db = Storage.connect(str(path))
    try:
        actual = content(db)
        for name, rows in expected.items():
            if name not in (
                "schema_version",
                "segment_revisions",
                "memory_items",
                "memory_versions",
            ):
                assert actual[name] == rows
        assert actual["segment_revisions"] == []  # Never invent historical caption revisions.
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert (
            db.execute(
                "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'staging'"
            ).fetchone()[0]
            > 0
        )
        assert (
            db.execute("SELECT count(*) FROM sqlite_master WHERE name='memory_scope'").fetchone()[0]
            == 1
        )
        db.execute("CREATE TABLE migration_once_marker(x)")
    finally:
        db.close()
    db = Storage.connect(str(path))
    assert [r[0] for r in db.execute("SELECT version FROM schema_version ORDER BY version")] == [
        1,
        2,
    ]
    db.close()


def test_online_wal_backup_restore_preserves_all_rows_and_recovery(tmp_path):
    directory = tmp_path / "data with spaces"
    store, project, meeting = seed(directory)
    before = content(store.disk)
    atomic_private(directory / "pairing-token", "FAKE_LOCAL_CREDENTIAL_NOT_BACKED_UP")
    (directory / ".env").write_text("DEEPSEEK_API_KEY=FAKE_NOT_BACKED_UP")
    destination = tmp_path / "backup with spaces"
    manifest = backup(directory, destination)  # Store and WAL remain open.
    assert manifest["counts"]["reports"] == 2
    assert set(p.name for p in destination.iterdir()) == {"copilot.sqlite3", "manifest.json"}
    assert "FAKE_LOCAL_CREDENTIAL" not in (destination / "copilot.sqlite3").read_bytes().decode(
        "latin1"
    )
    store.patch_project(project["id"], dict(name="Changed after backup"))
    store.close()
    result = restore(directory, destination)
    assert result["recovery"] and validate_backup(Path(result["recovery"]))
    with closing(sqlite3.connect(directory / "copilot.sqlite3")) as db:
        assert content(db) == before
    reopened = Storage(directory)
    assert reopened.project(project["id"])["name"] == "Upgrade synthetic"
    assert len(reopened.memory(meeting["id"])) == 1
    assert len(reopened.objects(meeting["id"], "reports")) == 2
    assert (
        reopened.evidence_revision(meeting["id"], "upgrade", 1)["text"] == "I will review API-17."
    )
    reopened.close()
    assert (directory / "pairing-token").read_text() == "FAKE_LOCAL_CREDENTIAL_NOT_BACKED_UP"


def test_backup_excludes_ram_sessions(tmp_path):
    store, _, _ = seed(tmp_path / "ram", memory=True)
    destination = tmp_path / "ram-backup"
    manifest = backup(tmp_path / "ram", destination)
    assert manifest["counts"]["meetings"] == manifest["counts"]["reports"] == 0
    assert "RAM meetings" in manifest["excluded"]
    store.close()


def test_restore_refuses_live_writer_and_bad_checksum_without_touching_data(tmp_path):
    directory = tmp_path / "data"
    store, _, _ = seed(directory)
    store.close()
    destination = tmp_path / "backup"
    backup(directory, destination)
    before = (directory / "copilot.sqlite3").read_bytes()
    with DataOwnership(directory):
        with pytest.raises(RuntimeError, match="DATA_BUSY"):
            restore(directory, destination)
    assert (directory / "copilot.sqlite3").read_bytes() == before
    with (destination / "copilot.sqlite3").open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(RuntimeError, match="BACKUP_CHECKSUM"):
        restore(directory, destination)
    assert (directory / "copilot.sqlite3").read_bytes() == before


def test_restore_replace_fault_preserves_current_and_recoverable_preimage(tmp_path):
    directory = tmp_path / "data"
    store, _, _ = seed(directory)
    expected = content(store.disk)
    store.close()
    destination = tmp_path / "backup"
    backup(directory, destination)
    original = os.replace

    def fail_stage(source, target):
        if Path(source).name.startswith("restore-stage-"):
            raise OSError("synthetic replace fault")
        return original(source, target)

    with patch("app.backup.os.replace", side_effect=fail_stage):
        with pytest.raises(OSError):
            restore(directory, destination)
    with closing(sqlite3.connect(directory / "copilot.sqlite3")) as db:
        assert content(db) == expected
    assert any((directory / "recovery").iterdir())


def test_atomic_credential_failure_keeps_previous_value(tmp_path):
    path = tmp_path / "pairing-token"
    atomic_private(path, "FAKE_OLD")
    with patch("app.ownership.os.replace", side_effect=OSError("synthetic")):
        with pytest.raises(OSError):
            atomic_private(path, "FAKE_NEW")
    assert path.read_text() == "FAKE_OLD"
    assert list(tmp_path.iterdir()) == [path]
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_rotation_invalidates_rest_and_open_websocket_preserving_meeting(client):
    store = client.app.state.store
    project = store.create_project(dict(name="Keep", description="", glossary={}))
    meeting = store.create_meeting(
        dict(
            project_id=project["id"],
            title="Keep",
            timezone="UTC",
            persistence_mode="local",
            demo=True,
            meeting_key=None,
        )
    )
    origin = "chrome-extension://" + "a" * 32
    with client.websocket_connect(
        "/api/v1/events", headers={"Origin": origin, "Host": "127.0.0.1:8765"}
    ) as ws:
        ws.send_json(dict(type="auth", protocol_version=1, token="test-pairing-token"))
        assert ws.receive_json()["type"] == "auth.ok"
        response = client.post("/api/v1/local/pairing/rotate")
        assert response.status_code == 200 and "token" not in response.json()
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    assert client.get("/api/v1/projects").status_code == 401
    config = client.app.state.provider
    assert config.key == ""  # Pairing rotation does not set a provider key.
    directory = Path(store.disk.execute("PRAGMA database_list").fetchone()[2]).parent
    new = (directory / "pairing-token").read_text().strip()
    assert len(new) >= 43 and new != "test-pairing-token"
    headers = {"Authorization": "Bearer " + new}
    assert client.get("/api/v1/meetings/" + meeting["id"], headers=headers).status_code == 200
    assert new not in response.text and new not in client.get("/ready").text
    with client.websocket_connect(
        "/api/v1/events", headers={"Origin": origin, "Host": "127.0.0.1:8765"}
    ) as ws:
        ws.send_json(dict(type="auth", protocol_version=1, token=new))
        assert ws.receive_json()["type"] == "auth.ok"


def test_shutdown_rejects_unverified_instance_and_requires_auth(client):
    assert client.post("/api/v1/local/shutdown", json={"instance": "wrong"}).status_code == 409
    assert not client.app.state.shutdown_requested.is_set()
    assert (
        client.post(
            "/api/v1/local/pairing/rotate", headers={"Authorization": ""}, json={}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/local/pairing/rotate", headers={"Origin": "https://evil.example"}, json={}
        ).status_code
        == 403
    )
    instance = client.get("/ready").json()["instance"]
    assert client.post("/api/v1/local/shutdown", json={"instance": instance}).status_code == 200
    assert client.app.state.shutdown_requested.is_set() and not client.get("/ready").json()["ready"]


def test_data_paths_are_project_relative_and_shutdown_failure_still_releases_resources(
    tmp_path, monkeypatch
):
    from app.config import ROOT as PROJECT_ROOT, data_directory

    monkeypatch.chdir(tmp_path)
    assert data_directory(".local") == PROJECT_ROOT / ".local"
    application = create_app(Config(tmp_path / "shutdown", "FAKE_PAIR", ()))

    async def failed_close():
        raise RuntimeError("synthetic close failure")

    with pytest.raises(RuntimeError, match="synthetic close failure"):
        with TestClient(application):
            application.state.provider.aclose = failed_close
    with DataOwnership(tmp_path / "shutdown"):
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        application.state.store.disk.execute("SELECT 1")


async def test_report_concurrency_and_total_budget_preserve_saved_versions(
    store, meeting, monkeypatch
):
    import asyncio
    from app import service as service_module
    from app.service import Service
    from app.retrieval import Retrieval
    from app.errors import AppError
    from app.llm import demo_report

    class SlowProvider:
        async def complete(self, context, *_):
            await asyncio.sleep(0.2)
            return demo_report(context["segments"])

    store.apply_caption(meeting["id"], caption("Could you clarify the next step?"))
    store.control(meeting["id"], dict(action="end", idempotency_key=uid()))
    service = Service(store, Retrieval(store, Semantic(Path("."))), SlowProvider())
    previous = service.save_report(meeting["id"], demo_report(store.transcript(meeting["id"])), 1)
    other = store.create_meeting(
        dict(
            project_id=meeting["project_id"],
            title="Other",
            timezone="UTC",
            persistence_mode="local",
            demo=False,
            meeting_key=None,
        )
    )
    store.control(other["id"], dict(action="end", idempotency_key=uid()))
    monkeypatch.setattr(service_module, "REPORT_TOTAL_SECONDS", 0.02)
    first = service.report(meeting["id"], 1)
    assert service.report(meeting["id"], 1) is first
    with pytest.raises(AppError) as error:
        service.report(other["id"], 0)
    assert error.value.code == "REPORT_BUSY"
    await asyncio.gather(*list(service.tasks))
    assert first["status"] == "error" and first["error"]["code"] == "REPORT_DEADLINE"
    assert service.get_report(previous["id"])["payload"] == previous["payload"]
    assert len(store.objects(meeting["id"], "reports")) == 1
    await service.shutdown()
    await service.retrieval.aclose()


def test_lifespan_cancels_open_provider_stream_and_waits_for_indexer(tmp_path):
    import asyncio
    import threading
    import time
    import httpx

    started = threading.Event()
    closed = threading.Event()
    index_started = threading.Event()
    index_finished = threading.Event()

    class HeldStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                started.set()
                yield b'data: {"choices":[{"delta":{"content":"{"}}]}\n\n'
                await asyncio.sleep(60)
            finally:
                closed.set()

    config = Config(tmp_path, "FAKE_PAIR", (), api_key="FAKE_PROVIDER")
    application = create_app(config)
    with TestClient(
        application, base_url="http://127.0.0.1:8765", headers={"Authorization": "Bearer FAKE_PAIR"}
    ) as client:
        store = application.state.store
        project = store.create_project(dict(name="Shutdown", description="", glossary={}))
        meeting = store.create_meeting(
            dict(
                project_id=project["id"],
                title="Stream",
                timezone="UTC",
                persistence_mode="local",
                demo=False,
                meeting_key=None,
            )
        )
        store.apply_caption(meeting["id"], caption("Could you clarify the next step?"))
        application.state.provider.transport = httpx.MockTransport(
            lambda _: httpx.Response(200, stream=HeldStream())
        )
        assert client.post(f"/api/v1/meetings/{meeting['id']}/suggest", json={}).status_code == 202
        assert started.wait(3)

        # Exercise the actual source worker and separate SQLite connection during shutdown.
        def delayed_sync(_self, _id):
            index_started.set()
            time.sleep(0.3)
            assert _self.store.disk.execute("SELECT 1").fetchone()[0] == 1
            index_finished.set()
            return dict(status="ready")

        with patch("app.main.Ingestion.sync", delayed_sync):
            thread = threading.Thread(
                target=lambda: client.post(
                    f"/api/v1/projects/{project['id']}/sources",
                    json=dict(kind="text", title="Held index", pasted_text="Synthetic"),
                )
            )
            thread.start()
            assert index_started.wait(3)
    thread.join(3)
    assert not thread.is_alive()
    assert closed.wait(1) and index_finished.is_set()
    with DataOwnership(tmp_path):
        pass
    reopened = Storage(tmp_path)
    assert reopened.meeting(meeting["id"])["status"] == "interrupted"
    reopened.close()


def test_real_runner_port_ownership_crash_restart_and_verified_stop(tmp_path):
    import socket
    import time
    import urllib.request
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    directory = tmp_path / "runner data with spaces"
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend"),
        "MEET_DATA_DIR": str(directory),
        "MEET_EXTENSION_ID": "",
        "MEET_DEV_ORIGIN": "",
        "DEEPSEEK_API_KEY": "",
    }
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            pytest.fail(
                "Port 8765 must be free for required process test; refusing to touch existing process."
            )

    def wait_ready():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/ready", timeout=1) as result:
                    if json.load(result)["ready"]:
                        return
            except (OSError, ValueError):
                time.sleep(0.05)
        raise AssertionError("Runner never ready")

    def launch():
        return subprocess.Popen(
            [sys.executable, "-m", "app.runner"],
            cwd=tmp_path,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    process = launch()
    try:
        wait_ready()
        second = subprocess.run(
            [sys.executable, "-m", "app.runner"], env=environment, capture_output=True, timeout=10
        )
        assert second.returncode != 0  # Port fails before opening/mutating the data directory.
        with pytest.raises(RuntimeError, match="DATA_BUSY"):
            DataOwnership(directory).acquire()
        token = (directory / "pairing-token").read_text().strip()

        def call(route, body):
            request = urllib.request.Request(
                "http://127.0.0.1:8765" + route,
                data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as result:
                return json.load(result)

        project = call("/api/v1/projects", dict(name="Crash preservation"))
        meeting = call(
            "/api/v1/meetings",
            dict(project_id=project["id"], title="Crash", timezone="UTC", demo=True),
        )
        process.kill()  # Abrupt on Windows and POSIX; SIGTERM would be graceful on Linux.
        process.wait(timeout=10)
        assert (directory / "runtime.json").exists()
        process = launch()
        wait_ready()
        with closing(sqlite3.connect(directory / "copilot.sqlite3")) as db:
            stored = json.loads(
                db.execute("SELECT payload FROM meetings WHERE id=?", (meeting["id"],)).fetchone()[
                    0
                ]
            )
        assert stored["status"] == "interrupted"
        identity = json.loads((directory / "runtime.json").read_text())
        identity["pid"] = (
            1  # PID is deliberately false; stop must use authenticated instance identity.
        )
        (directory / "runtime.json").write_text(json.dumps(identity))
        stopped = subprocess.run(
            [sys.executable, str(ROOT / "scripts/meet.py"), "stop", "--data-dir", str(directory)],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            timeout=45,
        )
        assert stopped.returncode == 0 and b"ownership released" in stopped.stdout
        process.wait(timeout=10)
        assert process.returncode == 0 and not (directory / "runtime.json").exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)

    class Foreign(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ready":true,"instance":"foreign"}')

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 8765), Foreign)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.runner"], env=environment, capture_output=True, timeout=10
        )
        assert result.returncode != 0
        (directory / "runtime.json").write_text('{"pid":1,"instance":"stale"}')
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/meet.py"), "stop", "--data-dir", str(directory)],
            env=environment,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode != 0 and b"PROCESS_UNVERIFIED" in result.stderr
        with urllib.request.urlopen("http://127.0.0.1:8765/ready") as response:
            assert json.load(response)["instance"] == "foreign"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
