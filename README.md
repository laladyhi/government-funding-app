# Government Funding AI (정부 지원사업 검색 · 매칭 서비스)

기업마당, K-Startup, 정부24 공공서비스(혜택) 등 여러 정부/공공기관의 지원사업
공고를 하나의 표준 구조로 모아 검색·열람할 수 있게 해주는 로컬 웹 애플리케이션입니다.

이 프로젝트는 정부기관이 공식 운영하는 서비스가 **아니며**, 각 기관이 공개한
Open API를 통해 공개된 공고 데이터를 그대로 수집·정리해서 보여주는 개인
프로젝트입니다. 모든 원본 데이터의 출처와 링크는 화면에 그대로 표시됩니다.

## 무엇을 하는 프로젝트인가

- 여러 기관마다 다른 API 응답 구조를 `StandardProgram`이라는 공통 형식으로
  변환해 하나의 SQLite DB에 저장합니다.
- 각 항목(신청기간, 지원대상, 지원금액 등)마다 **"확인된 사실 / AI 분석 /
  추정 / 미추출"** 상태를 표시해, 실제 API가 준 값과 임의로 채운 값을
  절대 섞지 않습니다.
- 원본 API 응답(raw)과 원본 첨부파일은 가공 전 상태 그대로 별도 보관합니다.
- 아직 연동되지 않은 기관은 코드 없이 "링크만 관리" 또는 "연동 후보"
  상태로만 표시됩니다 — 미확인 API를 추정으로 구현하지 않습니다.

## 데이터 출처 현황

| 기관 | 방식 | 현재 상태 |
|---|---|---|
| 기업마당 (bizinfo.go.kr) | Open API | 연동 완료, 운영 DB 20건 적재 |
| 창업진흥원 (K-Startup) | Open API (data.go.kr) | 연동 완료, 운영 DB 5건 적재 |
| 정부24 공공서비스(혜택) | Open API (odcloud.kr) | 연동 완료, 실제 호출·운영 DB 적재 완료 (5건) |
| 중소벤처기업진흥공단 (KOSMES) | Open API 예정 | 연동 후보 (요청 명세 미확인) |
| 한국콘텐츠진흥원 (KOCCA) | Open API | 연동 완료, 실제 호출·운영 DB 적재 완료 (4건) |
| 국민체육진흥공단 (KSPO) | Open API 예정 | 연동 후보 (키 발급 전) |
| 한국관광공사 / 영화진흥위원회 | 게시판 | 링크만 관리 (자동 수집 없음) |

각 출처의 상세 조사 근거와 확인일은 [docs/data-source-decision.md](docs/data-source-decision.md),
[docs/agency-coverage-survey.md](docs/agency-coverage-survey.md) 문서에 있습니다.

## 프로젝트 구조

```
.env.example        ← 필요한 환경변수 이름 목록 (실제 키 값은 없음)
collector/           ← 1단계: 기관별 API 어댑터 + 원본 데이터 수집
  adapters/            기관마다 하나씩(base.py 공통 규격 상속)
  raw/                 수집된 원본 응답 그대로 보관(가공 금지)
app/
  db/                  DB 마이그레이션, 적재 스크립트, 테스트
  data/                SQLite DB 파일(로컬 생성, 저장소에는 포함 안 됨)
  templates/           화면(HTML)
  server.py            Flask 웹 서버
docs/                각 단계의 조사/설계/의사결정 기록
requirements.txt
```

## 설치 및 실행 방법

### 0. 준비물

- Python 3.10 이상
- (선택) 사용할 기관의 Open API 인증키 — 없어도 이미 수집된 데이터로 화면은
  볼 수 있습니다. 새 데이터를 직접 수집하려는 기관만 키가 필요합니다.

### 1. 저장소 내려받기 및 패키지 설치

```bash
git clone <이 저장소 URL>
cd NEW_Project_HGIJ
pip install -r requirements.txt
```

### 2. 환경변수 설정 (API 키가 필요한 경우만)

```bash
cp .env.example .env
```

`.env` 파일을 열어 발급받은 키를 채워 넣습니다. 각 키를 어디서 발급받는지는
`.env.example`의 주석과 [docs/env-setup.md](docs/env-setup.md)를 참고하세요.

**`.env` 파일은 절대 커밋하거나 공유하지 마세요.** `.gitignore`에 이미
등록되어 있어 실수로 커밋되지 않도록 막혀 있습니다.

### 3. DB 생성 및 데이터 적재

```bash
python app/db/migrate.py
python app/db/load_bizinfo.py
```

더 자세한 단계별 안내(기관 추가, 재수집 등)는
[docs/local-run-guide.md](docs/local-run-guide.md)를 참고하세요.

### 4. 웹 화면 실행

```bash
python app/server.py
```

브라우저에서 `http://127.0.0.1:5000` 접속. 이 서버는 로컬 전용이며 외부에서
접속할 수 없습니다.

## 테스트

기관별 어댑터는 실제 네트워크 호출 없이 fixture(가상/샘플 응답)로 검증합니다.

```bash
python app/db/test_hash_consistency.py
python app/db/test_standard_source_pipeline.py
python app/db/test_kstartup_real_pipeline.py
python app/db/test_public_benefits_pipeline.py
```

## 보안 원칙

- API 키는 `.env`에만 저장하며 코드/로그/문서 어디에도 값을 직접 적지 않습니다.
- 키가 없는(`MISSING_KEY`) 상태에서는 해당 기관으로 어떤 네트워크 요청도
  보내지 않도록 모든 어댑터가 공통으로 `check_readiness()`를 거칩니다.
- 실제 API를 호출하는 스크립트는 호출 결과를 화면에 표시할 때도 키 값은
  마스킹해서 절대 출력하지 않습니다.
- 원본 데이터는 절대 임의로 값을 채우지 않고, 확인되지 않은 항목은
  "미추출"로 정직하게 표시합니다.
