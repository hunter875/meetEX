"""Ordered, transactional migrations; unknown/future/gapped histories fail closed."""

from pathlib import Path

from .ownership import schema_version
from .version import SCHEMA_VERSION


def migrate(db, directory=None):
    directory = directory or Path(__file__).parent / "migrations"
    migrations = sorted(directory.glob("*.sql"))
    versions = [int(file.stem) for file in migrations]
    if versions != list(range(1, SCHEMA_VERSION + 1)):
        raise RuntimeError(
            "MIGRATION_FILES: expected contiguous migration files for this source version."
        )
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_version'").fetchone()
    applied = (
        sorted(row[0] for row in db.execute("SELECT version FROM schema_version")) if exists else []
    )
    if schema_version(db) > SCHEMA_VERSION:
        raise RuntimeError(
            "SCHEMA_NEWER: database is newer than app; source rollback is not schema downgrade."
        )
    if applied != list(range(1, len(applied) + 1)):
        raise RuntimeError(
            "MIGRATION_HISTORY: incomplete migration history; restore known-good backup."
        )
    for version, migration in zip(versions, migrations):
        if version in applied:
            continue
        try:
            db.executescript(
                "BEGIN IMMEDIATE;\n"
                + migration.read_text("utf8")
                + f"\nINSERT OR IGNORE INTO schema_version VALUES({version});\nCOMMIT;"
            )
        except Exception:
            db.rollback()
            raise
