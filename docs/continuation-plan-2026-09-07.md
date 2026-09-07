# 2026-09-07 작업 재개 계획

**마지막 갱신**: 2026-09-04 (이 날짜의 모든 작업 반영됨)

## 현재까지 완료된 상태

### 데이터 출처 (`data_sources` 테이블 기준)

| 출처 | 상태 | 비고 |
|---|---|---|
| 기업마당 | **연결됨** | 20건 운영 DB 적재, 검증 완료 |
| K-Startup | **연동됨(부분)** | 실제 5건 테스트 → **운영 DB 적재 완료** (`source='kstartup'`) |
| 한국콘텐츠진흥원(KOCCA) | 승인대기 | 서비스키는 있으나 운영단계 심의승인 여부 미확인. 실제 호출 아직 안 함 |
| 국민체육진흥공단(KSPO) | 연동후보 | **공식 API 존재 확인됨**(`docs/kspo-api-feasibility.md`). Swagger 상세(End Point·필드 전체)는 미확보 |
| 중소벤처기업진흥공단(KOSMES) | 연동후보(확인 필요 유지) | 자체 Open API 포털은 있으나 "지원사업공고" 데이터셋 존재는 미확정 (`docs/kosmes-kto-kofic-kspo-survey.md`) |
| 한국관광공사 | 링크만관리 | 공고용 API 없음 확인됨. 게시판(touraz.kr) 크롤링만 가능 |
| 영화진흥위원회 | 링크만관리 | 공고용 API 없음 확인됨. 게시판 크롤링만 가능 |

### 운영 DB

- `programs` 총 **25건** = 기업마당 20건 + K-Startup 5건
- K-Startup 5건 적재 전 자동 백업 완료 (`app/data/backups/govfunding_before_kstartup_load_20260904_164221.sqlite3`)
- 원본 API 응답·출처 정보 보존 구조, 해시 정책(`raw-data-hash-policy.md`) 적용됨
- 여러 출처가 공유하는 표준 변환 구조(`StandardProgram`, `collector/adapters/`) 마련됨

### 검증 완료 사항

- 기업마당 지역·기관명 오표시 수정 (문제 1·2 해결, `data-quality-audit-20260904.md`)
- K-Startup 적재 후: 중복 방지, 첨부파일 임의생성 없음, `공공기관`/`민간` 기관명 미저장, 목록·검색·상세 화면 정상 확인
- API 키가 로그·문서·화면에 출력되지 않음 확인
- 원본 raw 파일은 전 과정에서 한 번도 수정되지 않음(매 작업마다 수정시각 비교로 확인)

---

## 9월 7일 시작 체크리스트

아래 순서로 진행을 제안한다. 상황에 따라 준비된 항목부터 먼저 진행해도 된다.

### 1. (사람이 먼저 할 일) KSPO Swagger 명세 확보

자동 조회로는 Swagger 상세표(정확한 End Point, 요청 파라미터, 응답 필드
전체 목록)를 열람하지 못했다 — K-Startup 때처럼 **브라우저로 직접 열어야
한다**.

1. 브라우저로 [data.go.kr/data/15107780/openapi.do](https://www.data.go.kr/data/15107780/openapi.do) 접속
2. Swagger UI 또는 "API 문서" 버튼 클릭
3. 요청변수 표, 출력결과(응답) 표를 캡처하거나, 제공되면 가이드 문서(zip/docx) 다운로드해 프로젝트 폴더에 저장
4. Claude Code에 전달: `"docs/kspo-api-feasibility.md 파일을 참고해서 [저장한 파일/캡처] 내용을 확인하고 KSPO 어댑터를 준비해줘"`

### 2. KOCCA 서비스키 상태 재확인

운영단계 심의승인이 완료됐는지 확인한 뒤, Claude Code에 전달:

```text
KOCCA_API_KEY 승인 상태를 확인해줘. 승인됐으면 5건 이하로 실제 테스트 호출을 진행해줘.
아직 안 됐으면 계속 fixture만 사용해줘.
```

### 3. KOSMES 지원사업공고 데이터셋 확인 (사람이 먼저 할 일)

`kosmes.or.kr/opendata` 포털은 로그인 후 스크립트 렌더링 페이지라 자동
조회로 확인하지 못했다. 브라우저로 직접 로그인해 "지원사업공고"류
데이터셋이 있는지 확인 후 결과를 Claude Code에 전달한다.

### 4. 위 세 가지 중 준비된 것부터

Swagger 명세(1번) 또는 KOSMES 데이터셋(3번) 중 무엇이 먼저 확보되든,
그 기관부터 다음 순서로 진행한다.

```text
1. 서비스키 신청 (필요한 경우)
2. .env에 저장 (KSPO_API_KEY= 또는 KOSMES_API_KEY=, 값은 채팅에 적지 않음)
3. 5건 이하 테스트 호출
4. 실제 필드명·날짜 형식 확인, fixture 작성
5. 첨부파일 URL 여부 확인 (없으면 임의로 만들지 않음)
6. 변환 결과만 먼저 보여주고, 별도 승인 후에만 운영 DB 적재
```

### 5. 한국관광공사·영화진흥위원회

API가 없는 것으로 이미 확인됨(`kosmes-kto-kofic-kspo-survey.md`). 자동
수집을 고려한다면 게시판 크롤링뿐인데, 그 전에 반드시:

- 이용약관 확인 (이번 조사에서 못함)
- robots.txt 재확인 (한국관광공사 touraz.kr은 이번 조회 실패 — 브라우저로 재확인 필요)
- `docs/pre-collection-checklist.md` 전체 항목 확인

이 확인 전까지는 계속 `링크만관리` 상태를 유지하고 크롤링하지 않는다.

---

## 절대 지키는 원칙 (매번 재확인)

- API 키를 채팅·문서·로그·화면에 출력하지 않는다.
- `.env`의 실제 키는 커밋하지 않는다 (`.gitignore`로 이미 보호됨).
- 공식 API·Swagger가 확인되지 않으면 자동 수집하지 않는다.
- 첨부파일 URL이나 지원금액을 추정해서 만들지 않는다.
- 원본 응답과 원문 출처를 보존한다 (raw 파일 수정 금지).
- 한 번에 전체 데이터를 수집하지 않는다 — 항상 5건 이하로 먼저 테스트.
- 운영 DB 적재 전 항상 백업하고, 적재 후 항상 건수·중복·화면을 검증한다.

## 참고 문서 색인

| 문서 | 내용 |
|---|---|
| `phase1-data-model.md` / `phase1-mvp-screens.md` | 최초 설계(데이터 구조·화면) |
| `data-source-decision.md` | 출처 확정 결정과 표기 원칙 |
| `agency-coverage-survey.md` | 문체부·중기부 6개 기관 최초 조사 |
| `kocca-adapter-feasibility.md` | KOCCA 연동 사전조사 |
| `kosmes-kto-kofic-kspo-survey.md` | KOSMES·관광공사·영화진흥위원회·KSPO 1차 비교조사 |
| `kspo-api-feasibility.md` | KSPO 심화조사 (API 존재 확인) |
| `raw-data-hash-policy.md` | 해시 계산 통일 기준 |
| `data-quality-audit-20260904.md` | 기업마당 데이터 품질 점검·수정 내역 |
| `adding-new-source.md` | 새 기관 추가 절차(비개발자용) |
| `testing-with-fixtures.md` | 픽스처 테스트 방법 |
| `pre-collection-checklist.md` | 실제 자동수집 시작 전 체크리스트 |
| `local-run-guide.md` / `env-setup.md` | 로컬 실행·키 관리 방법 |
