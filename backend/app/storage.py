from __future__ import annotations
import json
import sqlite3
import uuid
import time
from threading import RLock
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .config import DEFAULTS
from .errors import AppError


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decoded(rows):
    return [json.loads(row["payload"]) for row in rows]


class Storage:
    def __init__(self, data_dir: Path):
        self.session_lock = RLock()
        self.memory_update_timings = []
        data_dir.mkdir(parents=True, exist_ok=True)
        self.disk = self.connect(str(data_dir / "copilot.sqlite3"))
        try:
            self.ram = self.connect(":memory:")
            self.cleanup()
            with self.disk:
                for m in self.meetings():
                    if m["status"] in ("active", "paused"):
                        m["status"] = "interrupted"
                        self.save_meeting(self.disk, m)
                        self.gap(self.disk, m["id"], "backend_restart", certainty="possible")
        except Exception:
            self.disk.close()
            if hasattr(self, "ram"):
                self.ram.close()
            raise

    @staticmethod
    def connect(path):
        db = sqlite3.connect(path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        from .ownership import schema_version
        from .version import SCHEMA_VERSION

        if schema_version(db) > SCHEMA_VERSION:
            db.close()
            raise RuntimeError(
                "SCHEMA_NEWER: database is newer than this app; restore matching source or a pre-upgrade backup."
            )
        db.execute("PRAGMA foreign_keys=ON")
        if path != ":memory:":
            db.execute("PRAGMA journal_mode=WAL")
        try:
            db.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(content)")
            db.execute("DROP TABLE temp.fts_probe")
        except sqlite3.OperationalError:
            db.close()
            raise RuntimeError(
                "SQLite runtime lacks FTS5. Install official Python with SQLite FTS5 support."
            )
        from .migration import migrate

        try:
            migrate(db)
        except Exception:
            db.close()
            raise
        return db

    def close(self):
        try:
            self.disk.close()
        finally:
            self.ram.close()

    def settings(self):
        row = self.disk.execute("SELECT payload FROM settings WHERE id=1").fetchone()
        return {**DEFAULTS, **(json.loads(row[0]) if row else {})}

    def set_settings(self, patch):
        values = {**self.settings(), **patch}
        with self.disk:
            self.disk.execute("INSERT OR REPLACE INTO settings VALUES(1,?)", (dumps(values),))
        return values

    def projects(self):
        return [
            self.project(r[0])
            for r in self.disk.execute("SELECT id FROM projects ORDER BY created_at DESC")
        ]

    def project(self, id):
        row = self.disk.execute("SELECT * FROM projects WHERE id=?", (id,)).fetchone()
        if not row:
            raise AppError("NOT_FOUND", "Project not found", 404)
        p = dict(row)
        p["glossary"] = json.loads(p["glossary"])
        return p

    def create_project(self, body):
        p = dict(id=uid(), created_at=now(), **body)
        with self.disk:
            self.disk.execute(
                "INSERT INTO projects VALUES(?,?,?,?,?)",
                (p["id"], p["name"], p["description"], dumps(p["glossary"]), p["created_at"]),
            )
        return p

    def patch_project(self, id, body):
        p = {**self.project(id), **body}
        with self.disk:
            self.disk.execute(
                "UPDATE projects SET name=?,description=?,glossary=? WHERE id=?",
                (p["name"], p["description"], dumps(p["glossary"]), id),
            )
        return p

    def sources(self, project):
        self.project(project)
        return decoded(
            self.disk.execute("SELECT payload FROM sources WHERE project_id=?", (project,))
        )

    def source(self, id):
        row = self.disk.execute("SELECT payload FROM sources WHERE id=?", (id,)).fetchone()
        if not row:
            raise AppError("NOT_FOUND", "Source not found", 404)
        return json.loads(row[0])

    def save_source(self, s):
        self.disk.execute(
            "INSERT INTO sources(id,project_id,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (s["id"], s["project_id"], dumps(s)),
        )

    def db_for(self, id):
        for db in (self.ram, self.disk):
            if db.execute("SELECT 1 FROM meetings WHERE id=?", (id,)).fetchone():
                return db
        raise AppError("NOT_FOUND", "Meeting not found or memory session expired", 404)

    def meeting(self, id):
        db = self.db_for(id)
        return json.loads(
            db.execute("SELECT payload FROM meetings WHERE id=?", (id,)).fetchone()[0]
        )

    def meetings(self):
        return sorted(
            decoded(self.disk.execute("SELECT payload FROM meetings"))
            + decoded(self.ram.execute("SELECT payload FROM meetings")),
            key=lambda m: m["started_at"],
            reverse=True,
        )

    def save_meeting(self, db, m):
        db.execute("UPDATE meetings SET payload=? WHERE id=?", (dumps(m), m["id"]))

    def ensure_session_slot(self, exclude_id=None):
        """Caller holds session_lock across this check and the state commit."""
        if any(
            m["id"] != exclude_id and m["status"] in ("active", "paused") for m in self.meetings()
        ):
            raise AppError(
                "ACTIVE_MEETING",
                "End the active or paused meeting before starting/resuming another",
                409,
            )

    def create_meeting(self, body):
        with self.session_lock:
            project = self.project(body["project_id"])
            self.ensure_session_slot()
            meeting = dict(
                id=uid(),
                status="active",
                started_at=now(),
                ended_at=None,
                transcript_revision=0,
                capture_status="starting",
                last_caption_at=None,
                binding=None,
                self_speaker=None,
                confirmed_segment_ids=[],
                auto_mode=self.settings()["auto_mode"],
                epochs={},
                latest_request=None,
                pause_from=None,
                **body,
            )
            db = self.ram if meeting["persistence_mode"] == "memory" else self.disk
            with db:
                if db is self.ram:
                    db.execute(
                        "INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?)",
                        (
                            project["id"],
                            project["name"],
                            project["description"],
                            dumps(project["glossary"]),
                            project["created_at"],
                        ),
                    )
                db.execute(
                    "INSERT INTO meetings VALUES(?,?,?)",
                    (meeting["id"], meeting["project_id"], dumps(meeting)),
                )
            return meeting

    def transcript(self, id):
        return decoded(
            self.db_for(id).execute(
                "SELECT payload FROM caption_segments WHERE meeting_id=? ORDER BY rowid", (id,)
            )
        )

    def gap(self, db, id, reason, start=None, end=None, certainty="certain"):
        g = dict(id=uid(), reason=reason, from_at=start or now(), to_at=end, certainty=certainty)
        db.execute("INSERT INTO capture_gaps VALUES(?,?,?)", (g["id"], id, dumps(g)))
        return g

    def gaps(self, id):
        return decoded(
            self.db_for(id).execute("SELECT payload FROM capture_gaps WHERE meeting_id=?", (id,))
        )

    def control(self, id, body):
        # One process/worker: local and RAM share the same state-transition lock.
        # Replays return the recorded response without reapplying any transition.
        with self.session_lock:
            db = self.db_for(id)
            meeting = self.meeting(id)
            action = body["action"]
            old = db.execute(
                "SELECT response FROM controls WHERE meeting_id=? AND key=?",
                (id, body["idempotency_key"]),
            ).fetchone()
            if old:
                return json.loads(old[0])
            if action == "resume" and meeting["status"] in ("paused", "interrupted"):
                self.ensure_session_slot(exclude_id=id)
            with db:
                if body.get("reason") == "interrupted_pending_discarded":
                    self.gap(db, id, "interrupted_pending_discarded", certainty="possible")
                if meeting["status"] == "ended" and action == "end":
                    pass
                elif action == "pause" and meeting["status"] == "active":
                    meeting.update(status="paused", pause_from=now(), capture_status="paused")
                elif action == "resume" and meeting["status"] in ("paused", "interrupted"):
                    self.gap(
                        db,
                        id,
                        "pause" if meeting["status"] == "paused" else "interrupted",
                        meeting["pause_from"] or meeting["last_caption_at"] or now(),
                        now(),
                    )
                    meeting.update(status="active", pause_from=None, capture_status="starting")
                elif action == "end" and meeting["status"] in ("active", "paused", "interrupted"):
                    if body.get("reason") == "end_flush_timeout":
                        self.gap(db, id, "end_flush_timeout", certainty="possible")
                    if meeting["pause_from"]:
                        self.gap(db, id, "pause", meeting["pause_from"], now())
                    meeting.update(status="ended", ended_at=now(), capture_status="meeting_left")
                elif action == "interrupt" and meeting["status"] in ("active", "paused"):
                    self.gap(db, id, body.get("reason") or "tab_closed", certainty="possible")
                    meeting.update(status="interrupted", capture_status="disconnected")
                else:
                    raise AppError(
                        "INVALID_STATE", f"Cannot {action} a {meeting['status']} meeting", 409
                    )
                self.save_meeting(db, meeting)
                db.execute(
                    "INSERT INTO controls VALUES(?,?,?)",
                    (id, body["idempotency_key"], dumps(meeting)),
                )
            return meeting

    def apply_caption(self, id, event):
        db = self.db_for(id)
        m = self.meeting(id)
        e = event
        prior = db.execute(
            "SELECT ack FROM applied_events WHERE meeting_id=? AND event_id=?", (id, e["event_id"])
        ).fetchone()
        if prior:
            return json.loads(prior[0])
        changed = False
        with db:
            if m["status"] == "active":
                previous_seq = m["epochs"].get(e["capture_epoch"], 0)
                if e["seq"] > previous_seq + 1:
                    self.gap(db, id, "sequence_gap", certainty="possible")
                m["epochs"][e["capture_epoch"]] = max(previous_seq, e["seq"])
                row = db.execute(
                    "SELECT revision,epoch,payload FROM caption_segments WHERE meeting_id=? AND id=?",
                    (id, e["segment_id"]),
                ).fetchone()
                if row and row["epoch"] != e["capture_epoch"]:
                    raise AppError(
                        "SEGMENT_SCOPE", "Segment belongs to a different capture epoch", 409
                    )
                if not row or e["revision"] > row["revision"]:
                    old = json.loads(row["payload"]) if row else {}
                    if (
                        old.get("text") != e["text"] or old.get("speaker") != e["speaker_label"]
                    ) and e["segment_id"] in m.get("confirmed_segment_ids", []):
                        m["confirmed_segment_ids"].remove(e["segment_id"])
                        m["memory_revision_warnings"] = m.get("memory_revision_warnings", 0) + 1
                    seg = dict(
                        id=e["segment_id"],
                        capture_epoch=e["capture_epoch"],
                        revision=e["revision"],
                        speaker=e["speaker_label"],
                        text=e["text"],
                        stable=e["stable"],
                        observed_from=old.get("observed_from", e["observed_at"]),
                        observed_to=e["observed_at"],
                    )
                    db.execute(
                        "INSERT INTO caption_segments VALUES(?,?,?,?,?) ON CONFLICT(meeting_id,id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",
                        (seg["id"], id, e["capture_epoch"], e["revision"], dumps(seg)),
                    )
                    db.execute(
                        "INSERT INTO segment_revisions VALUES(?,?,?,?)",
                        (id, seg["id"], seg["revision"], dumps(seg)),
                    )
                    m["transcript_revision"] += 1
                    m["last_caption_at"] = e["observed_at"]
                    changed = True
                    from .meeting_memory import update

                    memory_began = time.perf_counter()
                    if update(db, m, seg):
                        for record in decoded(
                            db.execute("SELECT payload FROM suggestions WHERE meeting_id=?", (id,))
                        ):
                            record["stale"] = True
                            db.execute(
                                "UPDATE suggestions SET payload=? WHERE id=?",
                                (dumps(record), record["id"]),
                            )
                    self.memory_update_timings.append((time.perf_counter() - memory_began) * 1000)
                    self.memory_update_timings = self.memory_update_timings[-1000:]
                    for s in decoded(
                        db.execute("SELECT payload FROM suggestions WHERE meeting_id=?", (id,))
                    ):
                        if any(
                            x["id"] == seg["id"]
                            and (x["text"] != seg["text"] or x.get("speaker") != seg["speaker"])
                            for x in s["snapshot"]["segments"] + s["snapshot"].get("memory", [])
                        ):
                            s["stale"] = True
                            db.execute(
                                "UPDATE suggestions SET payload=? WHERE id=?", (dumps(s), s["id"])
                            )
            ack = dict(
                type="caption.ack",
                protocol_version=1,
                session_id=id,
                event_id=e["event_id"],
                server_revision=m["transcript_revision"],
                applied=changed,
                ignored_reason=None if m["status"] == "active" else m["status"],
            )
            self.save_meeting(db, m)
            db.execute(
                "INSERT INTO applied_events VALUES(?,?,?,?,?)",
                (id, e["event_id"], e["capture_epoch"], e["seq"], dumps(ack)),
            )
        return ack

    def objects(self, id, table):
        assert table in ("suggestions", "ai_requests", "reports")
        return decoded(
            self.db_for(id).execute(
                f"SELECT payload FROM {table} WHERE meeting_id=? ORDER BY rowid", (id,)
            )
        )

    def report_view(self, report):
        refs = report.get("evidence_snapshot", [])
        current = {s["id"]: s for s in self.transcript(report["meeting_id"])}
        changed = any(
            s["id"] not in current or current[s["id"]]["revision"] != s["revision"] for s in refs
        )
        changed = changed or (
            report.get("memory_revision") is not None
            and report["memory_revision"]
            != self.meeting(report["meeting_id"]).get("memory_revision", 0)
        )
        return {
            **dict(
                memory_snapshot=[],
                memory_revision=None,
                evidence_snapshot=[],
                historical_payload=None,
                reconciliation=None,
                edit_provenance=None,
            ),
            **report,
            "evidence_changed": changed,
        }

    def snapshot(self, id):
        return dict(
            **self.meeting(id),
            segments=self.transcript(id),
            gaps=self.gaps(id),
            suggestions=self.objects(id, "suggestions"),
            requests=self.objects(id, "ai_requests"),
            reports=[self.report_view(r) for r in self.objects(id, "reports")],
        )

    def memory(self, id):
        from .meeting_memory import rows

        return rows(self.db_for(id), id)

    def evidence_revision(self, id, segment_id, revision):
        row = (
            self.db_for(id)
            .execute(
                "SELECT payload FROM segment_revisions WHERE meeting_id=? AND segment_id=? AND revision=?",
                (id, segment_id, revision),
            )
            .fetchone()
        )
        if not row:
            raise AppError(
                "NOT_FOUND",
                "Evidence revision not available; legacy history was not fabricated",
                404,
            )
        return json.loads(row[0])

    def delete_meeting(self, id):
        db = self.db_for(id)
        with db:
            db.execute("DELETE FROM meetings WHERE id=?", (id,))

    def delete_project(self, id):
        self.project(id)
        for m in self.meetings():
            if m["project_id"] == id:
                self.delete_meeting(m["id"])
        with self.disk:
            self.disk.execute("DELETE FROM projects WHERE id=?", (id,))
        with self.ram:
            self.ram.execute("DELETE FROM projects WHERE id=?", (id,))

    def cleanup(self, at=None):
        at = at or datetime.now(timezone.utc)
        cutoff = at - timedelta(days=self.settings()["retention_days"])
        removed = []
        for m in self.meetings():
            if datetime.fromisoformat(m["ended_at"] or m["started_at"]) < cutoff:
                self.delete_meeting(m["id"])
                removed.append(m["id"])
        return removed
