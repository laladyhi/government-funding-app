-- data_sources 메타데이터를 실제 상태로 맞춘다.
--
-- kocca/kstartup은 이미 오래 전부터 실제 데이터가 적재되어 정상 작동
-- 중인데(2026-09-07 이후), data_sources 표만 예전 상태("승인대기"/
-- "연동후보")로 남아 있었다. programs 표를 직접 조회해 실제로 확인:
--   kocca    : programs.source='kocca'    4건 적재됨
--   kstartup : programs.source='kstartup' 5건 적재됨
-- 실제 데이터(programs)는 이 마이그레이션으로 전혀 건드리지 않는다 —
-- data_sources 메타데이터 표만 사실에 맞게 갱신한다.
--
-- e나라도움(enara)은 0003 마이그레이션 당시엔 존재조차 몰랐던 출처라
-- data_sources에 행 자체가 없었다. 2026-09-09 실제 연동 완료(738건
-- 적재)로 신규 등록한다.

UPDATE data_sources
SET
  connection_status = '연결됨',
  terms_notes = terms_notes
    || ' [2026-09-09 상태정정] 실제로는 이미 실제 API 연동 및 운영 DB 적재가'
    || ' 완료된 상태였음(programs 표에서 직접 확인) — data_sources 메타데이터만'
    || ' 예전 상태로 남아 있던 것을 바로잡음.'
WHERE source_key = 'kocca';

UPDATE data_sources
SET
  connection_status = '연결됨',
  terms_notes = terms_notes
    || ' [2026-09-09 상태정정] 실제로는 이미 실제 API 연동 및 운영 DB 적재가'
    || ' 완료된 상태였음(programs 표에서 직접 확인) — data_sources 메타데이터만'
    || ' 예전 상태로 남아 있던 것을 바로잡음.'
WHERE source_key = 'kstartup';

INSERT INTO data_sources (
  source_key, display_name, homepage_url, announcement_page_url,
  collection_method, connection_status, env_var_name, terms_notes, last_checked_at
) VALUES (
  'enara',
  'e나라도움·보조금24(국고보조금 통합관리)',
  'https://www.gosims.go.kr/',
  'https://www.bojo2.go.kr/',
  'API',
  '연결됨',
  'ENARA_API_KEY',
  '공공데이터포털 국고보조금 공모사업 API(apis.data.go.kr/1051000/MoefOpenAPI2025). 2026-09-09 실제 전체 수집(총 응답 197,936건 중 공고명·접수기간이 있는 738건 선별) 및 운영 DB 적재 완료. 원본이 XML 기반이라 값에 CDATA 래퍼가 남는 특이사항이 있어 collector/adapters/enara_adapter.py, app/db/action_summary.py에서 별도 정제함.',
  '2026-09-09'
);
