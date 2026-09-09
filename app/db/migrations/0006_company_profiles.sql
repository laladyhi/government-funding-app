-- 회사 프로필 저장 (AI 토큰을 쓰지 않는 규칙 기반 매칭 기능의 입력값).
-- 기존 programs/program_fields 등 지원사업 표는 전혀 건드리지 않는다 —
-- 완전히 새로운 표 하나만 추가한다. 개인정보가 아니라 "회사 단위" 속성만
-- 저장한다(대표자명, 사업자번호 등은 저장하지 않음).

CREATE TABLE company_profiles (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  name                  TEXT NOT NULL,               -- 화면 구분용 별칭(예: "우리 회사")
  region                TEXT,                        -- 소재지 (예: "경기", "서울")
  industry              TEXT,                        -- 업종 (자유 텍스트, 예: "제조업")
  founded_date          TEXT,                        -- 창업일 (YYYY-MM-DD, 있으면 이걸로 업력 계산)
  business_age_years    INTEGER,                     -- 업력(년) — founded_date가 없을 때 직접 입력
  employee_count        INTEGER,                     -- 직원 수
  revenue_range         TEXT,                        -- 매출 구간 (자유 텍스트, 예: "1억~10억")
  company_type          TEXT NOT NULL DEFAULT '확인 필요'
                          CHECK (company_type IN ('소상공인', '중소기업', '중견기업', '해당없음', '확인 필요')),
  exports                TEXT NOT NULL DEFAULT '확인 필요'
                          CHECK (exports IN ('예', '아니오', '확인 필요')),
  rnd                    TEXT NOT NULL DEFAULT '확인 필요'
                          CHECK (rnd IN ('예', '아니오', '확인 필요')),
  desired_fields        TEXT,                        -- 필요한 지원 분야, 쉼표로 구분한 자유 텍스트
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
