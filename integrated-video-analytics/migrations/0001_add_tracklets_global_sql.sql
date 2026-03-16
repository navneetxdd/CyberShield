CREATE TABLE IF NOT EXISTS tracklets (
  tracklet_id TEXT PRIMARY KEY,
  camera_id TEXT,
  start_ts TEXT,
  end_ts TEXT,
  frame_count INTEGER,
  aggregated_reid BLOB,
  aggregated_face BLOB,
  color_histogram BLOB,
  bbox_history TEXT,
  plate_assoc TEXT,
  resolved_global_id TEXT,
  enrichment_started_at TEXT,
  enrichment_completed_at TEXT,
  last_updated TEXT
);

CREATE TABLE IF NOT EXISTS global_identities (
  global_id TEXT PRIMARY KEY,
  created_at TEXT,
  last_seen_ts TEXT,
  last_seen_camera TEXT,
  face_embedding BLOB,
  reid_embedding BLOB,
  watchlist_flag INTEGER DEFAULT 0,
  watchlist_meta JSON,
  confidence REAL
);

CREATE TABLE IF NOT EXISTS identity_incidents (
  incident_id TEXT PRIMARY KEY,
  tracklet_id TEXT,
  candidate_global_id TEXT,
  reason TEXT,
  score REAL,
  created_at TEXT,
  resolved INTEGER DEFAULT 0,
  operator_action TEXT
);

CREATE TABLE IF NOT EXISTS vehicles (
  vehicle_id TEXT PRIMARY KEY,
  tracklet_id TEXT,
  first_seen_ts TEXT,
  last_seen_ts TEXT,
  camera_id TEXT,
  make_model TEXT,
  make_model_confidence REAL,
  color TEXT,
  color_confidence REAL
);

CREATE INDEX IF NOT EXISTS idx_tracklets_resolved_global_id ON tracklets(resolved_global_id);
CREATE INDEX IF NOT EXISTS idx_incidents_candidate_global_id ON identity_incidents(candidate_global_id);
CREATE INDEX IF NOT EXISTS idx_incidents_tracklet_id ON identity_incidents(tracklet_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_tracklet_id ON vehicles(tracklet_id);
