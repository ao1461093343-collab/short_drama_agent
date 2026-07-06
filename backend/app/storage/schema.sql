CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS script_projects (
  id UUID PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  platform VARCHAR(50) NOT NULL DEFAULT 'Douyin',
  genre VARCHAR(80) NOT NULL,
  brief TEXT NOT NULL DEFAULT '',
  bible JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS script_versions (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES script_projects(id) ON DELETE CASCADE,
  version_no INTEGER NOT NULL,
  status VARCHAR(40) NOT NULL,
  title VARCHAR(200) NOT NULL DEFAULT '',
  episode INTEGER,
  summary TEXT NOT NULL DEFAULT '',
  content JSONB NOT NULL DEFAULT '{}'::jsonb,
  review_report JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES script_projects(id) ON DELETE CASCADE,
  version_id UUID REFERENCES script_versions(id) ON DELETE CASCADE,
  source VARCHAR(120) NOT NULL,
  chunk_type VARCHAR(60) NOT NULL,
  text TEXT NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(1024),
  embedding_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  embedding_error TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  indexed_at TIMESTAMPTZ
);

ALTER TABLE script_projects ADD COLUMN IF NOT EXISTS brief TEXT NOT NULL DEFAULT '';
ALTER TABLE script_projects ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE script_versions ADD COLUMN IF NOT EXISTS title VARCHAR(200) NOT NULL DEFAULT '';
ALTER TABLE script_versions ADD COLUMN IF NOT EXISTS episode INTEGER;
ALTER TABLE script_versions ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES script_projects(id) ON DELETE CASCADE;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS version_id UUID REFERENCES script_versions(id) ON DELETE CASCADE;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_error TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS script_versions_project_created_idx
ON script_versions (project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS knowledge_chunks_project_type_idx
ON knowledge_chunks (project_id, chunk_type);

CREATE INDEX IF NOT EXISTS knowledge_chunks_project_created_idx
ON knowledge_chunks (project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_status_idx
ON knowledge_chunks (embedding_status, created_at);

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
