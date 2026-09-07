-- 2026-09-04 조사 결과 반영: 데이터 출처 "상태"만 갱신한다.
-- 이 마이그레이션은 어떤 외부 사이트에도 접속하지 않는다 — 이미 확인된
-- 조사 결과(docs/agency-coverage-survey.md)를 DB에 반영하는 것뿐이다.
--
-- 국민체육진흥공단(kspo)만 변경한다: '링크만관리' -> '연동후보'(API).
-- 단, 실제로 API 존재/명세를 아직 확인한 것은 아니므로 api_notes에
-- 그 불확실성을 명확히 남긴다 — 확인됐다고 과장하지 않는다.
--
-- 중소벤처기업진흥공단(kosmes), 한국관광공사(kto), 영화진흥위원회(kofic)는
-- 이미 요청하신 상태(각각 연동후보/링크만관리/링크만관리)와 일치하므로
-- 이 마이그레이션에서 건드리지 않는다.
--
-- homepage_url, announcement_page_url, last_checked_at은 SET 절에서
-- 제외해 기존 값을 그대로 보존한다. terms_notes(조사 근거 URL이 담긴
-- 필드)는 기존 내용을 지우지 않고 새 메모를 뒤에 이어 붙인다(||) —
-- data_sources 테이블에는 organizations와 달리 별도의 api_notes
-- 컬럼이 없으므로 terms_notes 하나에 근거와 상태메모를 함께 둔다.

UPDATE data_sources
SET
  collection_method = 'API',
  connection_status = '연동후보',
  terms_notes = terms_notes
    || ' [2026-09-04 상태변경] "공고 전용 API 연동 후보"로 변경. 단, API 자체의 '
    || '존재나 명세(Swagger/OpenAPI)는 아직 확인되지 않은 상태 — 이전 조사에서는 '
    || '자체 API를 발견하지 못했다. 실제 API 키 발급 전까지 어댑터 코드나 실제 '
    || '호출은 작성하지 않는다. 다음 단계: (1) 공식 Swagger(OpenAPI) 명세 확보, '
    || '(2) 서비스키 신청/발급, (3) 5건 이하 테스트 호출 준비. 순서상 (1)이 선행되어야 한다.'
WHERE source_key = 'kspo';
