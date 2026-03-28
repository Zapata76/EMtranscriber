CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  source_file_path TEXT NOT NULL,
  working_audio_path TEXT,
  status TEXT NOT NULL,
  language_detected TEXT,
  language_selected TEXT,
  model_name TEXT,
  device_used TEXT,
  compute_type TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  FOREIGN KEY(project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS speakers (
  speaker_key TEXT NOT NULL,
  job_id TEXT NOT NULL,
  display_name TEXT,
  color_tag TEXT,
  is_manually_named INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  PRIMARY KEY (speaker_key, job_id),
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);

CREATE TABLE IF NOT EXISTS transcript_segments (
  segment_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  speaker_key TEXT,
  speaker_name_resolved TEXT,
  text TEXT NOT NULL,
  source_type TEXT NOT NULL,
  confidence REAL,
  order_index INTEGER NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);

CREATE TABLE IF NOT EXISTS transcript_words (
  word_id TEXT PRIMARY KEY,
  segment_id TEXT NOT NULL,
  start_ms INTEGER,
  end_ms INTEGER,
  speaker_key TEXT,
  text TEXT NOT NULL,
  probability REAL,
  order_index INTEGER NOT NULL,
  FOREIGN KEY(segment_id) REFERENCES transcript_segments(segment_id)
);

CREATE TABLE IF NOT EXISTS job_context_hints (
  job_id TEXT PRIMARY KEY,
  language_hint TEXT,
  domain_context TEXT,
  hotwords_json TEXT,
  glossary_json TEXT,
  expected_participants_json TEXT,
  expected_entities_json TEXT,
  expected_acronyms_json TEXT,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);
