# 4개 기관 공식 데이터 제공 방식 조사 보고서

**조사일**: 2026-09-04
**조사 방법**: 각 기관 robots.txt 1회 열람, 공공데이터포털(data.go.kr) 검색·페이지 열람, 웹 검색. **대량 요청이나 게시판 크롤링은 하지 않았다. 새 수집 코드도 작성하지 않았다.**

---

## 결과 표

| 기관명 | 공식 홈페이지 | 공고 페이지 | API/RSS | 키 신청 여부 | 주요 필드 | 자동 수집 가능성 | 근거 URL | 다음 행동 |
|---|---|---|---|---|---|---|---|---|
| 중소벤처기업진흥공단(KOSMES) | [kosmes.or.kr](https://www.kosmes.or.kr/) | **확인 필요** — 사업마다 개별 페이지로 분산돼 있어 단일 통합 게시판을 찾지 못함(예: `SHSBI035M0.do`) | 자체 Open API 포털 존재(kosmes.or.kr/opendata) — 단, "지원사업공고" 전용 데이터셋 존재 여부는 페이지가 스크립트 렌더링이라 미확인. RSS는 검색으로 못 찾음 | 필요(자체 포털 인증키) | 확인 불가(데이터셋 상세를 열지 못함) | 낮음~확인 필요 | [kosmes.or.kr/opendata](https://www.kosmes.or.kr/opendata/portal/openapi/openApiListPage.do), [robots.txt](https://www.kosmes.or.kr/robots.txt) | 자체 포털에서 "지원사업" 카테고리를 사람이 직접 로그인해 확인 필요(스크립트 렌더링이라 자동조회 한계) |
| 한국관광공사 | [knto.or.kr](https://knto.or.kr/) | [touraz.kr/announcementList](https://touraz.kr/announcementList) (관광기업지원센터 별도 포털) | 관광정보(TourAPI, LOD 15만건)만 확인됨 — **기업지원 공고용 API는 없음**(확인됨). RSS 확인 안 됨 | 관광정보 API는 필요(참고용, 공고와 무관) | 해당없음(공고용 API 자체가 없음) | API 경로 없음 → 게시판 크롤링만 가능 | [touraz.kr](https://touraz.kr/announcementList), [api.visitkorea.or.kr](https://api.visitkorea.or.kr) | touraz.kr의 robots.txt·이용약관을 사람이 브라우저로 직접 재확인(이번 자동조회는 실패) 후 게시판 구조 상세조사 |
| 영화진흥위원회 | [kofic.or.kr](https://www.kofic.or.kr/) | [사업공지 게시판](https://www.kofic.or.kr/kofic/business/prom/promotionBoardList.do) | KOBIS(박스오피스/영화정보) API만 확인됨 — **지원사업 공고용 API는 없음**(확인됨). RSS 확인 안 됨 | 해당없음(공고용 API 없음) | 해당없음 | API 없음 → 게시판 크롤링만 가능. robots.txt가 전면 허용(`Allow: /`)이라 기술적 장벽은 낮음 | [robots.txt](https://www.kofic.or.kr/robots.txt), [사업공지 게시판](https://www.kofic.or.kr/kofic/business/prom/promotionBoardList.do) | 이용약관 확인 후 게시판 페이지네이션·상세URL·첨부파일 구조 조사(KOCCA 때와 동일한 절차) |
| **국민체육진흥공단** | [kspo.or.kr](https://kspo.or.kr/) | [스포츠산업지원 알림마당](https://spobiz.kspo.or.kr/front/bbs/bbsList.do?boardId=BBS0001&topMenuSeq=2) | **공식 Open API 확인됨** — "서울올림픽기념국민체육진흥공단_스포츠산업지원 지원사업 정보"(공공데이터포털 등록, 제공기관=국민체육진흥공단 확인). RSS 확인 안 됨 | **필요**(공공데이터포털 인증키) | 공고제목, 접수기간 시작일/종료일, 접수종료시간, 등록일자 확인(전체 필드는 Swagger 명세 별도 확인 필요 — 지원대상/상세URL/첨부파일 포함 여부 미확인) | **높음** — 4개 기관 중 유일하게 지원사업 공고 전용 공식 API 확인됨 | [data.go.kr/data/15107780](https://www.data.go.kr/data/15107780/openapi.do), [robots.txt](https://spobiz.kspo.or.kr/robots.txt) | **가장 우선순위 높음** — 서비스키 신청 → Swagger 명세로 정확한 요청 파라미터·전체 응답 필드 확인 → KOCCA와 동일한 절차로 소량 실제 테스트 |

---

## robots.txt 확인 결과 (참고)

| 기관 | 대상 도메인 | 결과 |
|---|---|---|
| KOSMES | kosmes.or.kr | `Googlebot`에게 결제(PTS) 관련 8개 경로만 차단. 일반 공고/사업 페이지는 제한 없음 |
| 한국관광공사 | touraz.kr | **robots.txt를 정상적으로 읽지 못함**(404 오류 페이지 반환) — 파일이 없거나 이번 자동조회가 실패한 것일 수 있어, 실제 수집 전에는 사람이 브라우저로 재확인 필요 |
| 영화진흥위원회 | kofic.or.kr | `User-agent: *`, `Allow: /` — 전면 허용, 차단 경로 없음 |
| 국민체육진흥공단 | spobiz.kspo.or.kr | 전체 봇에 `/mng/`(관리자 추정)만 차단. 그 외 공고 게시판 등은 제한 없음 |

이용약관은 4개 기관 모두 이번 조사에서 직접 확인하지 못했다 — 실제 수집을 시작하기 전에는 반드시 확인이 필요하다(`docs/pre-collection-checklist.md` 참고).

---

## 결론 및 제안 우선순위

1. **국민체육진흥공단** — 지원사업 공고 전용 공식 API가 실제로 존재함을 확인. 4개 기관 중 다음 단계(서비스키 신청) 진행을 제안할 만한 유일한 곳.
2. **중소벤처기업진흥공단** — 자체 API 포털은 있으나 "지원사업공고" 데이터셋 존재를 이번 조사로는 확정하지 못함. 사람이 직접 포털에 로그인해 확인하는 절차가 필요.
3. **한국관광공사 / 영화진흥위원회** — 둘 다 지원사업 공고용 공식 API가 없는 것으로 확인됨. API가 없으므로 자동 수집을 하려면 게시판 크롤링이 유일한 방법인데, 이번 조사에서는 이용약관·robots.txt를 완전히 확인하지 못해 크롤링 여부를 아직 판단할 수 없다. `docs/data-source-decision.md`의 "링크만관리" 상태를 유지하는 것을 제안한다.

이번 조사에서는 코드를 작성하지 않았고, 실제 데이터 수집·API 호출도 하지 않았다.
