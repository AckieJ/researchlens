-- ResearchLens schema (PostgreSQL + pgvector). Idempotent: safe to run repeatedly.
-- NOTE: vector(768) must match EMBED_DIM in .env.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  question text NOT NULL,
  parsed jsonb,
  status text DEFAULT 'queued',
  progress jsonb DEFAULT '{}'::jsonb,
  error text,
  embedding vector(768),
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS papers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid REFERENCES workspaces(id) ON DELETE CASCADE,
  doi text, openalex_id text, title text, year int, authors text, venue text,
  url text, oa_url text, license text,
  text_level text DEFAULT 'abstract',          -- full | abstract
  full_text text, abstract text,
  retraction_status text DEFAULT 'none',       -- none | retracted | corrected | concern
  cited_by_count int DEFAULT 0,
  refs text[] DEFAULT '{}',                    -- OpenAlex ids this paper cites
  lane text,                                   -- A | B | D (first lane that found it)
  kept boolean DEFAULT false,
  is_upload boolean DEFAULT false,
  is_new boolean DEFAULT false,                -- uploaded after the graph was built
  expanded_from uuid,                          -- seed paper that led to this one (second ring)
  confidence text DEFAULT 'high',              -- low = Scholar result not resolved to a DOI
  scholar_links jsonb,
  embedding vector(768),
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS papers_ws_idx ON papers(workspace_id);
CREATE INDEX IF NOT EXISTS papers_emb_idx ON papers USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS paper_sources (
  paper_id uuid REFERENCES papers(id) ON DELETE CASCADE,
  lane text, query text, found_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS claims (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid, paper_id uuid REFERENCES papers(id) ON DELETE CASCADE,
  claim_text text, intervention text, outcome text, outcome_family text,
  direction text, significance text, effect_size text,
  population text, sample_n int, design text, duration text, measure text,
  limitations text, quote text, location text,
  embedding vector(768)
);
CREATE INDEX IF NOT EXISTS claims_ws_idx ON claims(workspace_id);
CREATE INDEX IF NOT EXISTS claims_paper_idx ON claims(paper_id);
CREATE INDEX IF NOT EXISTS claims_emb_idx ON claims USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS claim_edges (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid, claim_a uuid REFERENCES claims(id) ON DELETE CASCADE,
  claim_b uuid REFERENCES claims(id) ON DELETE CASCADE,
  label text,            -- supports_compatible | genuine_contradiction | apparent_contradiction | related_not_comparable | unresolved
  factors text[], confidence real, reason text, quotes jsonb,
  sim real, comparability jsonb,
  impact text,           -- strengthens | challenges | qualifies | leaves_unanswered (new-paper evaluation)
  UNIQUE (claim_a, claim_b)
);
CREATE INDEX IF NOT EXISTS edges_ws_idx ON claim_edges(workspace_id);

CREATE TABLE IF NOT EXISTS paper_scores (
  workspace_id uuid, paper_id uuid, relevance real, sector int, angle real, parent_paper uuid,
  PRIMARY KEY (workspace_id, paper_id)
);

CREATE TABLE IF NOT EXISTS flags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid, kind text,   -- limitation | weak_claim | library_gap | retraction
  description text, claim_ids uuid[] DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS fetch_cache (
  url_hash text PRIMARY KEY, url text, fetched_at timestamptz DEFAULT now(), body text
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid, role text, content text, cited_claims uuid[] DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS impact_reports (
  paper_id uuid PRIMARY KEY, workspace_id uuid, report jsonb, summary text,
  created_at timestamptz DEFAULT now()
);

-- Paper-to-paper lines are a summary of claim-level edges, never independent facts.
CREATE OR REPLACE VIEW paper_edges AS
SELECT e.workspace_id,
       CASE WHEN ca.paper_id < cb.paper_id THEN ca.paper_id ELSE cb.paper_id END AS paper_a,
       CASE WHEN ca.paper_id < cb.paper_id THEN cb.paper_id ELSE ca.paper_id END AS paper_b,
       e.label, count(*) AS n
FROM claim_edges e JOIN claims ca ON ca.id = e.claim_a JOIN claims cb ON cb.id = e.claim_b
GROUP BY 1, 2, 3, 4;
