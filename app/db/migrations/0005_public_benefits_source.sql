-- 정부24 "대한민국 공공서비스(혜택)" API를 데이터 출처 레지스트리에 등록한다.
--
-- 이 마이그레이션은 data_sources 테이블에 신규 행을 하나 추가할 뿐,
-- programs/organizations 등 다른 표는 전혀 건드리지 않는다. 실제 공고
-- 데이터(운영 DB의 programs 25건)는 이 마이그레이션과 무관하게 그대로
-- 유지된다.
--
-- 값의 근거:
--   - connection_status = '연결됨': 2026-09-07 실제 serviceList 호출
--     성공(소상공인 필터 5건 확인)로 확정. 승인 대기가 아니라 이미 승인된
--     "행정안전부_대한민국 공공서비스(혜택) 정보" 데이터셋(개발 계정)이다.
--   - env_var_name = 'PUBLIC_BENEFITS_API_KEY': .env에 이미 존재하는 변수명
--     그대로 사용(collector/adapters/public_benefits_adapter.py 참고).
--   - terms_notes의 근거 URL: data.go.kr/data/15113968 (사용자가 이전에
--     직접 확인해 전달한 값, docs/env-setup.md에도 동일하게 기록됨).

INSERT INTO data_sources (
  source_key, display_name, homepage_url, announcement_page_url,
  collection_method, connection_status, env_var_name, terms_notes, last_checked_at
) VALUES (
  'public_benefits',
  '정부24 공공서비스(혜택)',
  'https://www.gov.kr/',
  'https://www.data.go.kr/data/15113968/openapi.do',
  'API',
  '연결됨',
  'PUBLIC_BENEFITS_API_KEY',
  '행정안전부 제공, data.go.kr/data/15113968. 2026-09-07 serviceList 실제 호출 성공(cond[사용자구분::LIKE]=소상공인, 5건). 목록/상세 응답의 필드명이 서로 다름(접수기관/전화문의 vs 접수기관명/문의처) — collector/adapters/public_benefits_adapter.py 참고. 지원조건(JA코드)은 의미 미확정으로 원문만 보존.',
  '2026-09-07'
);
