CREATE TABLE segment_revisions(meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE, segment_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(meeting_id,segment_id,revision));
CREATE TABLE memory_items(meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE, id TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(meeting_id,id));
CREATE TABLE memory_versions(meeting_id TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(meeting_id,id,version), FOREIGN KEY(meeting_id,id) REFERENCES memory_items(meeting_id,id) ON DELETE CASCADE);
CREATE INDEX memory_scope ON memory_items(meeting_id,project_id);
