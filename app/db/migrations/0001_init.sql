-- Phase 1 초기 스키마
-- 원칙: 산업분류/기관유형/관계유형은 코드가 아니라 이 스키마의 "행(row)"으로 관리한다.
-- 즉, 새 값이 필요하면 INSERT 한 줄이면 되고 코드를 고칠 필요가 없다.

-- ── 코드성 값(하드코딩 대신 데이터로 관리하는 값) ─────────────────────────

CREATE TABLE organization_types (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE relationship_types (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE classification_axes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE classification_schemes (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  axis_id        INTEGER NOT NULL REFERENCES classification_axes(id),
  name           TEXT NOT NULL,
  version        TEXT,
  effective_date TEXT,
  status         TEXT NOT NULL DEFAULT '사용중'
);

-- ── 기관 및 기관관계 ────────────────────────────────────────────────────

CREATE TABLE organizations (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  name                   TEXT NOT NULL UNIQUE,  -- 표시명 (Phase1은 이름으로 동일기관 식별)
  org_type_id            INTEGER REFERENCES organization_types(id),
  homepage_url           TEXT,
  external_ref           TEXT,   -- 외부 시스템 식별자(있으면)
  data_collection_method TEXT,   -- API / 웹크롤링 / 수동
  last_collected_at      TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 기관 ↔ 기관의 "확인된" 소속/감독 관계. AI가 임의로 만들지 않는다 —
-- confirmation_status가 '확인됨'인 것만 화면 트리에 노출한다.
CREATE TABLE organization_relationships (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  from_org_id           INTEGER NOT NULL REFERENCES organizations(id),
  to_org_id             INTEGER NOT NULL REFERENCES organizations(id),
  relationship_type_id  INTEGER NOT NULL REFERENCES relationship_types(id),
  confirmation_status   TEXT NOT NULL CHECK (confirmation_status IN ('확인됨','확인필요','추정')),
  source_reference      TEXT,
  confirmed_at          TEXT,
  valid_from            TEXT,
  valid_to              TEXT,
  created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 관계가 수정될 때마다 이력을 남기는 자리 (Phase1은 구조만, 실제 갱신 로직은 이후 추가)
CREATE TABLE organization_relationship_changes (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  relationship_id INTEGER NOT NULL REFERENCES organization_relationships(id),
  changed_at      TEXT NOT NULL DEFAULT (datetime('now')),
  change_note     TEXT
);

-- ── 산업/기술(및 지원분야) 분류 ────────────────────────────────────────

-- 산업이든 기술이든 "지원분야"든 같은 트리 구조로 표현한다.
-- display_name은 언제든 바꿔도 되지만, id로 연결된 다른 데이터는 깨지지 않는다.
CREATE TABLE classification_nodes (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  scheme_id           INTEGER NOT NULL REFERENCES classification_schemes(id),
  parent_node_id      INTEGER REFERENCES classification_nodes(id),
  standard_code       TEXT,
  display_name        TEXT NOT NULL,
  status              TEXT NOT NULL DEFAULT '사용중' CHECK (status IN ('사용중','폐기됨','통합됨')),
  merged_into_node_id INTEGER REFERENCES classification_nodes(id),
  created_at          TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(scheme_id, display_name)
);

CREATE TABLE classification_node_name_history (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id          INTEGER NOT NULL REFERENCES classification_nodes(id),
  old_display_name TEXT NOT NULL,
  changed_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── 지원사업 ────────────────────────────────────────────────────────────

-- 목록 화면에 빠르게 보여줄 "정리된 요약값"만 여기 둔다.
-- 세부 항목과 출처는 program_fields + source_documents가 담당한다.
CREATE TABLE programs (
  id                          INTEGER PRIMARY KEY AUTOINCREMENT,
  source                      TEXT NOT NULL,           -- 예: 'bizinfo'
  source_item_id              TEXT NOT NULL,           -- 예: pblancId
  title                       TEXT,
  status_computed             TEXT,
  application_period_display  TEXT,
  amount_display               TEXT,
  target_company_display      TEXT,
  region_display               TEXT,
  first_collected_at          TEXT NOT NULL,
  last_updated_at             TEXT NOT NULL,
  latest_raw_hash              TEXT,
  UNIQUE(source, source_item_id)  -- 중복 저장 방지의 핵심 제약
);

CREATE TABLE program_organization_roles (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id    INTEGER NOT NULL REFERENCES programs(id),
  org_id        INTEGER NOT NULL REFERENCES organizations(id),
  role_type_id  INTEGER NOT NULL REFERENCES relationship_types(id),
  UNIQUE(program_id, org_id, role_type_id)
);

CREATE TABLE program_classifications (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id  INTEGER NOT NULL REFERENCES programs(id),
  node_id     INTEGER NOT NULL REFERENCES classification_nodes(id),
  link_basis  TEXT NOT NULL DEFAULT '원문명시',  -- 원문명시 / AI분류 / 사람검수
  UNIQUE(program_id, node_id)
);

-- ── 출처 및 원본 보존 ───────────────────────────────────────────────────

-- 웹페이지 원문, 첨부파일 등 "이 지원사업에 대한 근거 문서" 목록.
CREATE TABLE source_documents (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id     INTEGER NOT NULL REFERENCES programs(id),
  document_type  TEXT NOT NULL,   -- '웹페이지' / '첨부파일' / 'API원문'
  source_org     TEXT,            -- 예: '기업마당'
  url            TEXT,
  file_name      TEXT,
  collected_at   TEXT NOT NULL,
  content_hash   TEXT
);

-- 공고의 항목(필드) 하나하나가 어떤 값이고, 얼마나 신뢰할 수 있고(확인상태),
-- 어느 출처 문서에서 나왔는지를 기록한다. 상세화면의 "확인된 사실 / 출처" 표시가
-- 이 테이블 하나로 만들어진다.
CREATE TABLE program_fields (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id            INTEGER NOT NULL REFERENCES programs(id),
  field_name            TEXT NOT NULL,
  field_value           TEXT,               -- NULL 허용: 값이 없으면 없는 대로 저장(추정 금지)
  confirmation_status   TEXT NOT NULL CHECK (
                            confirmation_status IN ('확인된 사실','AI 분석','추정','미추출','해당없음')
                          ),
  source_document_id    INTEGER REFERENCES source_documents(id),
  page_number           INTEGER,
  section_text          TEXT,
  collected_at          TEXT NOT NULL
);

-- API가 실제로 돌려준 응답을 원문 그대로 보존 (감사/재처리용).
CREATE TABLE raw_api_responses (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  source           TEXT NOT NULL,
  source_item_id   TEXT,               -- 페이지 단위 원본은 NULL
  response_type    TEXT NOT NULL CHECK (response_type IN ('page','item')),
  raw_json         TEXT NOT NULL,
  collected_at     TEXT NOT NULL,
  content_hash     TEXT
);

-- ── 조회 성능을 위한 최소 인덱스 ───────────────────────────────────────
CREATE INDEX idx_program_fields_program_id ON program_fields(program_id);
CREATE INDEX idx_source_documents_program_id ON source_documents(program_id);
CREATE INDEX idx_program_classifications_program_id ON program_classifications(program_id);
CREATE INDEX idx_raw_api_responses_source_item ON raw_api_responses(source, source_item_id);

-- ── 초기 코드성 값 시딩 (하드코딩이 아니라 "초기 데이터") ───────────────
-- 새로운 유형이 필요하면 코드를 고치지 않고 이 테이블에 INSERT 한 줄만 추가하면 된다.

INSERT INTO organization_types (name) VALUES
  ('정부'), ('중앙부처'), ('산하기관'), ('유관기관'),
  ('지방자치단체'), ('지역기관'), ('협회'), ('기타');

INSERT INTO relationship_types (name, description) VALUES
  ('소속', '기관 간 공식 소속 관계'),
  ('감독', '상위기관의 감독 관계'),
  ('산하', '산하기관 관계'),
  ('주관', '지원사업을 실제로 수행/운영'),
  ('공동주관', '둘 이상의 기관이 함께 운영'),
  ('운영위탁', '운영을 위탁받음'),
  ('소관', '예산/정책 관할 (기업마당 jrsdInsttNm에 대응)');

INSERT INTO classification_axes (name, description) VALUES
  ('지원분야분류', '기업마당 등 API가 실제로 제공하는 지원 유형 분류(경영/기술/수출/인력 등)'),
  ('산업분류', '제조/바이오/AI-SW/콘텐츠 등 산업 분류 — Phase1 API 응답에는 없음, 추후 채움');

INSERT INTO classification_schemes (axis_id, name, version, status)
  SELECT id, name || ' v1', '1', '사용중' FROM classification_axes;
