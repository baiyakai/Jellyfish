-- 2026-04-03
-- 为分镜提取确认流程新增中间状态结构：
-- 1. shots.skip_extraction
-- 2. shots.last_extracted_at
-- 3. shot_extracted_candidates 表

BEGIN;

ALTER TABLE shots
  ADD COLUMN skip_extraction BOOLEAN NOT NULL DEFAULT 0;

ALTER TABLE shots
  ADD COLUMN last_extracted_at DATETIME NULL;

CREATE TABLE shot_extracted_candidates (
  id INTEGER PRIMARY KEY AUTO_INCREMENT,
  shot_id VARCHAR(64) NOT NULL,
  candidate_type VARCHAR(32) NOT NULL,
  candidate_name VARCHAR(255) NOT NULL,
  candidate_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  linked_entity_id VARCHAR(64) NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'extraction',
  payload JSON NULL,
  confirmed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_shot_extracted_candidates_shot
    FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE CASCADE,
  CONSTRAINT uq_shot_extracted_candidates_shot_type_name
    UNIQUE (shot_id, candidate_type, candidate_name),
  CONSTRAINT ck_shot_extracted_candidates_type
    CHECK (candidate_type IN ('character', 'scene', 'prop', 'costume')),
  CONSTRAINT ck_shot_extracted_candidates_status
    CHECK (candidate_status IN ('pending', 'linked', 'ignored'))
);

CREATE INDEX ix_shot_extracted_candidates_shot_id
  ON shot_extracted_candidates (shot_id);

CREATE INDEX ix_shot_extracted_candidates_status
  ON shot_extracted_candidates (candidate_status);

CREATE INDEX ix_shot_extracted_candidates_type
  ON shot_extracted_candidates (candidate_type);

COMMIT;
