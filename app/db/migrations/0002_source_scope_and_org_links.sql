-- Phase 1 데이터 출처 확정 반영.
-- 기업마당(bizinfo)을 Phase 1 기본 데이터 출처로 확정하면서,
-- "기관이 이 DB에 어떻게 등록되었는지"를 구분해서 기록한다.
-- 이 마이그레이션은 데이터(행)만 추가한다 — 수집 코드는 추가하지 않는다.

ALTER TABLE organizations ADD COLUMN announcement_page_url TEXT;
ALTER TABLE organizations ADD COLUMN registration_status TEXT NOT NULL DEFAULT '기업마당경유'
  CHECK (registration_status IN ('기업마당경유', '링크만관리', '연동후보'));
ALTER TABLE organizations ADD COLUMN source_reference TEXT;
ALTER TABLE organizations ADD COLUMN api_notes TEXT;

-- registration_status 의미:
--   기업마당경유 : 기업마당이 수집한 공고 안에서 기관명이 확인됨 (현재 자동 반영 대상)
--   링크만관리   : 자체 API/RSS가 확인되지 않아, 공식 링크만 등록하고 자동 수집은 하지 않음
--   연동후보     : 자체 Open API 존재가 확인되어 다음 단계 연동 후보로 기록 (코드 미작성)

-- ── 그룹3: 기업마당 게재 이력은 있으나 자체 API가 확인되지 않은 기관 ──────
-- docs/agency-coverage-survey.md (2026-09-04 조사) 근거. 자동 수집하지 않고
-- 기관명/공식 홈페이지/공식 공고 페이지/출처만 등록한다.

INSERT INTO organizations (name, org_type_id, homepage_url, announcement_page_url, registration_status, source_reference)
SELECT '한국콘텐츠진흥원', id, 'https://www.kocca.kr/', 'https://www.kocca.kr/kocca/pims/list.do?menuNo=204104', '링크만관리', 'docs/agency-coverage-survey.md (2026-09-04 조사)'
FROM organization_types WHERE name = '산하기관';

INSERT INTO organizations (name, org_type_id, homepage_url, announcement_page_url, registration_status, source_reference)
SELECT '한국관광공사', id, 'https://knto.or.kr/', 'https://touraz.kr/announcementList', '링크만관리', 'docs/agency-coverage-survey.md (2026-09-04 조사)'
FROM organization_types WHERE name = '산하기관';

INSERT INTO organizations (name, org_type_id, homepage_url, announcement_page_url, registration_status, source_reference)
SELECT '영화진흥위원회', id, 'https://www.kofic.or.kr/', 'https://www.kofic.or.kr/kofic/business/prom/promotionBoardList.do', '링크만관리', 'docs/agency-coverage-survey.md (2026-09-04 조사)'
FROM organization_types WHERE name = '산하기관';

INSERT INTO organizations (name, org_type_id, homepage_url, announcement_page_url, registration_status, source_reference)
SELECT '국민체육진흥공단', id, 'https://kspo.or.kr/', 'https://spobiz.kspo.or.kr/front/bbs/bbsList.do?boardId=BBS0001&topMenuSeq=2', '링크만관리', 'docs/agency-coverage-survey.md (2026-09-04 조사)'
FROM organization_types WHERE name = '산하기관';

-- ── 그룹2: 자체 Open API 존재가 확인되어 "연동 후보"로만 기록 (코드 없음) ──

INSERT INTO organizations (name, org_type_id, homepage_url, announcement_page_url, registration_status, source_reference, api_notes)
SELECT '창업진흥원', id, 'https://www.k-startup.go.kr/', 'https://www.k-startup.go.kr/web/main/mainSection0.do', '연동후보', 'docs/agency-coverage-survey.md (2026-09-04 조사)',
  'K-Startup 공공데이터포털 Open API 확인됨 (data.go.kr/data/15125364) — 지원사업공고/사업소개/콘텐츠/통계 4종 엔드포인트. Phase1 미연동, 코드 미작성.'
FROM organization_types WHERE name = '산하기관';

INSERT INTO organizations (name, org_type_id, homepage_url, announcement_page_url, registration_status, source_reference, api_notes)
SELECT '중소벤처기업진흥공단', id, 'https://www.kosmes.or.kr/', NULL, '연동후보', 'docs/agency-coverage-survey.md (2026-09-04 조사)',
  'Open API 포털 확인됨 (kosmes.or.kr/opendata/portal/openapi) — 인증키 발급 방식. Phase1 미연동, 코드 미작성.'
FROM organization_types WHERE name = '산하기관';
