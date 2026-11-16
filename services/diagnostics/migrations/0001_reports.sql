CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  delivered INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX reports_queue ON reports(delivered, received_at);
