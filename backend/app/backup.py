"""SQLite online snapshots and stopped, atomic restores. No credential files."""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .ownership import DataOwnership, schema_version
from .version import APP_VERSION, SCHEMA_VERSION


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)


def checksum(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inspect_database(path):
    with closing(readonly(path)) as db:
        version = schema_version(db)
        if not 1 <= version <= SCHEMA_VERSION:
            raise RuntimeError("SCHEMA_UNSUPPORTED: use matching app or an earlier backup.")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("BACKUP_INTEGRITY: database is damaged.")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("BACKUP_FOREIGN_KEY: database relations are invalid.")
        # Core tables must exist; integrity_check alone accepts an empty SQLite file.
        counts = {
            name: db.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for name in ("projects", "sources", "meetings", "caption_segments", "reports")
        }
    return dict(schema_version=version, counts=counts)


def snapshot(source, destination):
    deadline = time.monotonic() + 30

    def progress(*_):
        if time.monotonic() > deadline:
            raise RuntimeError(
                "BACKUP_BUSY: snapshot exceeded 30 seconds; retry after stopping backend."
            )

    with closing(readonly(source)) as original, closing(sqlite3.connect(destination)) as target:
        original.backup(target, pages=128, progress=progress, sleep=0.05)
        target.execute("PRAGMA journal_mode=DELETE")
    return inspect_database(destination)


def backup(directory: Path, destination: Path):
    destination = destination.resolve()
    if destination.exists():
        raise RuntimeError(
            "BACKUP_EXISTS: choose a new destination; existing backups are never overwritten."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".meet-backup-", dir=destination.parent))
    try:
        database = temporary / "copilot.sqlite3"
        info = snapshot(directory / "copilot.sqlite3", database)
        manifest = dict(
            format=1,
            app_version=APP_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
            **info,
            sha256=checksum(database),
            contents=["copilot.sqlite3"],
            excluded=[
                "RAM meetings",
                "pairing-token",
                "provider API key",
                ".env",
                "model cache",
                "external source files",
            ],
        )
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
        os.replace(temporary, destination)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def validate_backup(directory):
    manifest = json.loads((directory / "manifest.json").read_text("utf8"))
    database = directory / "copilot.sqlite3"
    if manifest.get("format") != 1 or manifest.get("contents") != ["copilot.sqlite3"]:
        raise RuntimeError("BACKUP_FORMAT: unsupported manifest.")
    if checksum(database) != manifest.get("sha256"):
        raise RuntimeError("BACKUP_CHECKSUM: backup changed; restore refused.")
    info = inspect_database(database)
    if info["schema_version"] != manifest.get("schema_version") or info["counts"] != manifest.get(
        "counts"
    ):
        raise RuntimeError("BACKUP_MANIFEST: database does not match manifest.")
    return manifest


def restore(directory: Path, source: Path):
    # Validate before acquiring or changing the target. Only the fixed database is restored.
    manifest = validate_backup(source)
    with DataOwnership(directory):
        target = directory / "copilot.sqlite3"
        descriptor, filename = tempfile.mkstemp(
            prefix="restore-stage-", suffix=".sqlite3", dir=directory
        )
        os.close(descriptor)
        stage = Path(filename)
        try:
            snapshot(source / "copilot.sqlite3", stage)
            recovery = None
            if target.exists():
                recovery = (
                    directory
                    / "recovery"
                    / (
                        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                        + "-"
                        + os.urandom(4).hex()
                    )
                )
                backup(directory, recovery)
                # Drain the previous WAL before atomic replacement. Never mix old WAL with new DB.
                with closing(sqlite3.connect(target, timeout=3)) as db:
                    result = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if result[0]:
                        raise RuntimeError(
                            "RESTORE_BUSY: another SQLite connection prevents checkpoint; restore refused."
                        )
                for suffix in ("-wal", "-shm"):
                    Path(str(target) + suffix).unlink(missing_ok=True)
            os.replace(stage, target)
            return dict(
                restored=True,
                schema_version=manifest["schema_version"],
                recovery=str(recovery) if recovery else None,
                credentials="unchanged on this machine; backups never import credentials",
            )
        finally:
            stage.unlink(missing_ok=True)
