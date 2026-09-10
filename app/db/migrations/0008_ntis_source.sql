-- NTIS public_project API 출처 등록.
-- 실제 승인키 값은 DB에 저장하지 않고 .env의 NTIS_API_KEY만 사용한다.
INSERT OR IGNORE INTO data_sources (
  source_key, display_name, homepage_url, announcement_page_url,
  collection_method, connection_status, env_var_name, terms_notes, last_checked_at
) VALUES (
  'ntis', 'NTIS 국가R&D 과제검색', 'https://www.ntis.go.kr/',
  'https://www.ntis.go.kr/rndopen/api/mng/apiMain.do', 'API', '연동후보',
  'NTIS_API_KEY',
  '2025 매뉴얼 확인: REST XML public_project 엔드포인트, 승인키(apprvKey) 필요. 기업지원 공고와 R&D 과제는 별도 출처로 관리.',
  '2026-09-10'
);
