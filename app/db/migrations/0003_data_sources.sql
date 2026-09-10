-- 여러 기관의 API/RSS/게시판을 나중에 쉽게 추가할 수 있도록
-- "데이터 출처 레지스트리"를 도입한다. organizations(기관 정체성/계층)와는
-- 별개로, "이 데이터를 어떻게 수집하는가"만 관리하는 테이블이다.
--
-- 여기 들어가는 URL은 전부 이전 조사 문서(docs/agency-coverage-survey.md,
-- docs/kocca-adapter-feasibility.md, docs/data-source-decision.md)에서
-- 이미 확인해 둔 값만 그대로 재사용한다. 이번 마이그레이션 작성 중에는
-- 어떤 외부 사이트에도 새로 접속하지 않았다 — 확인 못 한 새 URL은
-- 만들어 넣지 않는다.

CREATE TABLE data_sources (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  source_key            TEXT NOT NULL UNIQUE,   -- programs.source와 관례적으로 맞춤(예: 'bizinfo')
  display_name          TEXT NOT NULL,
  homepage_url          TEXT,
  announcement_page_url TEXT,
  collection_method     TEXT NOT NULL CHECK (collection_method IN ('API', 'RSS', '게시판', '링크만관리')),
  connection_status     TEXT NOT NULL CHECK (connection_status IN ('연결됨', '승인대기', '연동후보', '링크만관리')),
  env_var_name          TEXT,                   -- 링크만관리는 키가 없으므로 NULL 허용
  terms_notes           TEXT,                   -- 이용약관/출처 메모 (실제 키 값은 여기 절대 넣지 않음)
  last_checked_at       TEXT,
  created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 서로 다른 출처(source)에서 같은 공고가 들어올 수 있어, "같은 사업일 수
-- 있는 후보"를 관리할 자리를 미리 만들어둔다. 지금은 활성 출처가
-- 기업마당 하나뿐이라 실제 비교 대상이 없으므로, 표만 만들고 자동 판별
-- 로직은 이번에 넣지 않는다 (출처가 2개 이상 실제로 붙은 뒤에 채울 예정).
CREATE TABLE cross_source_duplicate_candidates (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id_a      INTEGER NOT NULL REFERENCES programs(id),
  program_id_b      INTEGER NOT NULL REFERENCES programs(id),
  similarity_score  REAL,
  match_basis       TEXT,     -- 예: '제목유사도', '기관일치+기간겹침'
  status            TEXT NOT NULL DEFAULT '검토대기'
                       CHECK (status IN ('검토대기', '같은사업확인', '다른사업확인')),
  detected_at       TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at       TEXT,
  UNIQUE(program_id_a, program_id_b)
);

CREATE INDEX idx_cross_dup_program_a ON cross_source_duplicate_candidates(program_id_a);
CREATE INDEX idx_cross_dup_program_b ON cross_source_duplicate_candidates(program_id_b);

-- ── 데이터 출처 시딩 ──────────────────────────────────────────────────

INSERT INTO data_sources (source_key, display_name, homepage_url, announcement_page_url, collection_method, connection_status, env_var_name, terms_notes, last_checked_at) VALUES
  ('bizinfo', '기업마당', 'https://www.bizinfo.go.kr/', 'https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do', 'API', '연결됨', 'BIZINFO_API_KEY', 'Phase 1 기본 데이터 출처로 확정. docs/data-source-decision.md 참고.', '2026-09-04'),

  ('kocca', '한국콘텐츠진흥원', 'https://www.kocca.kr/', 'https://www.kocca.kr/kocca/pims/list.do?menuNo=204104', 'API', '승인대기', 'KOCCA_API_KEY', '공공데이터포털 Open API 서비스키 발급됨(운영단계 심의승인 대기 여부 확인 필요). docs/kocca-adapter-feasibility.md 참고. 실제 응답 필드명은 승인 후 반드시 대조할 것.', '2026-09-04'),

  ('kstartup', '창업진흥원(K-Startup)', 'https://www.k-startup.go.kr/', 'https://www.k-startup.go.kr/web/main/mainSection0.do', 'API', '연동후보', 'KSTARTUP_API_KEY', '공공데이터포털에 지원사업공고 Open API 존재 확인(data.go.kr/data/15125364). 아직 키 미발급. docs/agency-coverage-survey.md 참고.', '2026-09-04'),

  ('ntis', 'NTIS 국가R&D 과제검색', 'https://www.ntis.go.kr/', 'https://www.ntis.go.kr/rndopen/api/mng/apiMain.do', 'API', '연동후보', 'NTIS_API_KEY', '2025 매뉴얼 확인: REST XML public_project 엔드포인트, 승인키(apprvKey) 필요. 기업지원 공고와 R&D 과제는 성격이 다르므로 별도 출처로 관리.', '2026-09-10'),

  ('kosmes', '중소벤처기업진흥공단', 'https://www.kosmes.or.kr/', NULL, 'API', '연동후보', 'KOSMES_API_KEY', '자체 Open API 포털 존재 확인(kosmes.or.kr/opendata). 공고 게시판 URL은 미확인이라 비워둠 — 임의로 만들지 않음. docs/agency-coverage-survey.md 참고.', '2026-09-04'),

  ('kto', '한국관광공사', 'https://knto.or.kr/', 'https://touraz.kr/announcementList', '게시판', '링크만관리', NULL, '기업지원 공고는 별도 포털(투어라즈)에서 운영. 자체 API 미확인. docs/agency-coverage-survey.md 참고.', '2026-09-04'),

  ('kofic', '영화진흥위원회', 'https://www.kofic.or.kr/', 'https://www.kofic.or.kr/kofic/business/prom/promotionBoardList.do', '게시판', '링크만관리', NULL, 'KOBIS(입장권통계) API는 있으나 사업공고용 아님. docs/agency-coverage-survey.md 참고.', '2026-09-04'),

  ('kspo', '국민체육진흥공단', 'https://kspo.or.kr/', 'https://spobiz.kspo.or.kr/front/bbs/bbsList.do?boardId=BBS0001&topMenuSeq=2', '게시판', '링크만관리', NULL, '기업지원 공고는 별도 사이트(스포츠산업지원)에서 운영. 자체 API 미확인. docs/agency-coverage-survey.md 참고.', '2026-09-04');
