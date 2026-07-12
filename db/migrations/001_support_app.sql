-- Support application store (tickets + guide). Own database — not nocloud commercial DB.

CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  appliance_id TEXT NOT NULL,
  status TEXT NOT NULL,
  bundle_json TEXT NOT NULL,
  diagnosis_json TEXT,
  error TEXT,
  github_issue_url TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_appliance ON tickets(appliance_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at);

CREATE TABLE IF NOT EXISTS guide_sessions (
  id TEXT PRIMARY KEY,
  locale TEXT NOT NULL DEFAULT 'en',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS guide_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES guide_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_guide_messages_session
  ON guide_messages(session_id, created_at);
