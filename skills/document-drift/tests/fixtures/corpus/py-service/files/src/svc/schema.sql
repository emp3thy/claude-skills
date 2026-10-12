CREATE TABLE IF NOT EXISTS items (
    key TEXT PRIMARY KEY,
    value BLOB NOT NULL,
    expires_at INTEGER
);
