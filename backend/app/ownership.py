"""Single-process data ownership. The OS lock, never the PID, is authoritative."""

import json
import os
from pathlib import Path


class DataOwnership:
    def __init__(self, directory: Path):
        self.directory = directory
        self.handle = None

    def acquire(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        handle = (self.directory / "writer.lock").open("a+b")
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                # Lock a byte even when the persistent file was initially empty.
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise RuntimeError(
                "DATA_BUSY: another process owns this data directory; stop it first."
            ) from error
        self.handle = handle
        return self

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()


def atomic_private(path: Path, text: str):
    """Atomic replacement, no partially-written credential; restrict POSIX mode."""
    import secrets

    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "nt":
            import subprocess

            account = os.environ["USERDOMAIN"] + "\\" + os.environ["USERNAME"]
            result = subprocess.run(
                ["icacls", str(temporary), "/inheritance:r", "/grant:r", account + ":(F)"],
                capture_output=True,
            )
            if result.returncode:
                raise RuntimeError(
                    "CREDENTIAL_PERMISSIONS: cannot restrict credential ACL to the current Windows account."
                )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def schema_version(db):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_version'").fetchone()
    return (
        max((row[0] for row in db.execute("SELECT version FROM schema_version")), default=0)
        if exists
        else 0
    )


def write_identity(directory, instance):
    atomic_private(directory / "runtime.json", json.dumps(dict(pid=os.getpid(), instance=instance)))
