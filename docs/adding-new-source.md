# 새 기관(데이터 출처)을 추가하는 방법

이 문서는 개발자가 아니어도 "어떤 순서로 무엇을 해야 하는지" 감을 잡을
수 있도록 쓴 안내서다. 실제 코드 수정이 필요한 단계는 Claude Code에게
"N번 기관 어댑터 만들어줘" 라고 요청하면 되고, 이 문서는 그 전후로
사람이 직접 확인/준비해야 하는 것이 무엇인지를 정리한 것이다.

## 전체 그림

```
1. 기관 조사        (사람 + Claude)  — 이미 조사된 기관은 건너뜀
2. data_sources 등록 (DB 마이그레이션) — 기관 정보를 DB에 기록
3. 어댑터 작성       (코드)          — collector/adapters/에 파일 하나 추가
4. 픽스처로 테스트    (코드+실행)      — 실제 키 없이 구조만 검증
5. 키 발급/승인 대기  (사람)          — 기관 공공데이터포털/자체 신청
6. .env에 키 저장    (사람)          — 절대 채팅/문서에 값 적지 않기
7. 실측 1회 테스트    (코드, 소량)     — 실제 응답과 ASSUMED_FIELDS 대조
8. 정식 연동         (코드)          — 실제 수집 시작
```

지금 이 프로젝트는 1~4단계까지 6개 기관(한국콘텐츠진흥원, 창업진흥원,
중소벤처기업진흥공단, 한국관광공사, 영화진흥위원회, 국민체육진흥공단)에
대해 준비되어 있다. 5번(키 발급)부터는 기관마다 사람이 직접 해야 한다.

## 1단계 — 기관 조사 (이미 한 적 없는 새 기관이라면)

Claude에게 "OO기관 연동 사전조사 해줘"라고 요청한다. 확인할 것:
- 공식 홈페이지, 공식 공고 게시판 URL
- 자체 Open API 또는 공공데이터포털 등록 여부
- RSS 제공 여부
- robots.txt, 이용약관상 자동수집 제한 여부

이미 조사된 기관은 `docs/agency-coverage-survey.md`,
`docs/kocca-adapter-feasibility.md`를 참고한다.

## 2단계 — `data_sources` 테이블에 등록

새 마이그레이션 파일(`app/db/migrations/000N_add_XXX_source.sql`)을 만들어
아래처럼 한 줄 추가한다 (Claude에게 요청하면 된다).

```sql
INSERT INTO data_sources (source_key, display_name, homepage_url, announcement_page_url,
  collection_method, connection_status, env_var_name, terms_notes, last_checked_at)
VALUES ('새기관코드', '기관 표시명', '홈페이지URL', '공고페이지URL',
  'API'|'RSS'|'게시판'|'링크만관리',
  '연결됨'|'승인대기'|'연동후보'|'링크만관리',
  '환경변수이름 또는 NULL',
  '이용약관/출처 메모 (실제 키 값은 절대 넣지 않음)',
  '조사일(YYYY-MM-DD)');
```

**중요**: `homepage_url`/`announcement_page_url`은 실제로 확인한 URL만
넣는다. 확인 못 한 값은 `NULL`로 두고 "확인 필요"라고 메모한다 — 그럴듯한
URL을 추측해서 채우지 않는다.

## 3단계 — 어댑터 파일 만들기

`collector/adapters/새기관코드_adapter.py` 파일 하나를 새로 만든다.
`collector/adapters/kocca_adapter.py`를 그대로 본떠서 만들면 된다 —
그 파일이 지켜야 하는 틀(`SourceAdapter`)은 `collector/adapters/base.py`에
정의되어 있고, 이 틀 자체는 고칠 필요가 없다.

체크리스트:
- [ ] `source_key`가 `data_sources.source_key`와 정확히 같은 문자열인가
- [ ] `env_var_name`이 실제 계획한 환경변수 이름과 같은가 (링크만관리는 `None`)
- [ ] `fetch_list()`가 `check_readiness()`부터 확인하고, 실제 URL이 확정되기 전엔 호출을 막아두었는가
- [ ] `to_standard_program()`이 `StandardProgram`의 12개 필드를 전부 채우는가 (모르는 값은 `None`)
- [ ] 신청기간이 날짜 형식이 아니면 `application_start`/`application_end`를 `None`으로 두는가 (날짜를 지어내지 않기)

## 4단계 — 픽스처(가상 데이터)로 테스트

실제 응답을 모르는 상태에서도, 예상되는 필드명으로 가짜 샘플 파일을
`collector/fixtures/새기관코드_sample_response.json`에 만들어 테스트할 수
있다. 방법은 `docs/testing-with-fixtures.md` 참고.

## 5~6단계 — 실제 키 발급 및 `.env` 저장

기관 공공데이터포털(대부분 data.go.kr)에서 서비스키를 신청한다.
발급받으면 **절대 채팅이나 문서에 값을 적지 말고**, 프로젝트 최상위
`.env` 파일을 직접 열어서 추가한다.

```
새환경변수이름=발급받은키값
```

`.env.example`에는 값 없이 변수 이름만 추가한다 (이미 있는 항목들 참고).

## 7단계 — 실측 1회 테스트 (키 발급 후, 코드 수정 필요)

이 단계는 실제 네트워크 요청이 발생하므로 반드시 사람이 "지금 해도 된다"
고 명시적으로 요청해야 진행한다. Claude에게 "OO 어댑터 실제 응답 1건만
테스트해줘, 5건 이하로 제한해줘"처럼 **건수를 제한해서** 요청한다.
이때 확인할 것:
- 실제 응답 필드명이 어댑터의 `ASSUMED_FIELDS`와 같은가 → 다르면 그
  자리에서 고친다
- 첨부파일 URL이 응답에 포함되는가
- 페이지네이션 파라미터가 예상과 같은가

## 8단계 — 정식 연동

7단계가 문제없이 끝나면, `data_sources.connection_status`를 `연결됨`으로
바꾸고, 정기적으로 수집을 실행할지(스케줄링)는 별도로 논의해서 결정한다.
스케줄링은 이 문서 범위 밖이다 — 사람이 명시적으로 요청할 때만 다룬다.
