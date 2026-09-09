"""
한국콘텐츠진흥원(KOCCA) 어댑터 — 지원사업 게시판 Open API
(요청 URL: https://kocca.kr/api/pims/List.do).

2026-09-07: 사용자가 첨부한 공식 명세서(한국콘텐츠진흥원_지원사업_API_명세서.pdf)와
그 직후 실제 호출(collector/test_kocca_api.py, 4건 수신, INFO-000)로
아래 URL·필드명이 전부 확인되었다. 더 이상 추정이 아니다.

⚠️ 명세서 자체의 내부 불일치 (실제 호출로 해소함, 명세서 문서 오탈자로 판단):
  - 응답 필드 "분류": 명세서의 요청/출력 파라미터 표는 "cata"라고 적혀 있었지만,
    명세서의 샘플 JSON과 실제 호출 응답 모두 "cate"였다. 실제 값인 "cate"를
    쓴다. 주의: 목록 조회 요청 파라미터 이름도 "cate"(게시판 카테고리 1~4)라서
    "요청의 cate"와 "응답 항목의 cate"가 이름이 같다 — 서로 다른 것이니
    혼동하지 않도록 REAL_FIELDS에서는 내부 이름을 "category"로 구분해 둔다.
  - 등록일 필드: 명세서 표는 "regDate"라고 적혀 있었지만, 명세서 샘플 JSON과
    실제 응답 모두 "regDt"였다. "regDt"를 쓴다.
  - 응답 메시지 필드: 명세서 표는 "resultMsg"라고 적혀 있었지만, 명세서 샘플
    JSON과 실제 응답 모두 "resultMgs"(오타)였다. 실제 값인 "resultMgs"를 쓴다.

확인된 사실:
  - 응답은 최상위에 "INFO" 객체 하나로 감싸여 있다: INFO.resultCode,
    INFO.resultMgs, INFO.list, INFO.listCount, INFO.pageNo, INFO.numOfRows.
  - list 안 각 항목의 실제 키: title, intcNoSeq, cate, hit, regDt, link,
    startDt, endDt, content. (2026-09-07 실 호출로 확인)
  - 목록 응답에는 지원대상(target)·첨부파일 관련 필드가 없다(명세서에도,
    실제 응답에도 없음) — 임의로 만들어 넣지 않는다.
  - link 값은 스킴(https://)이 없는 상태로 온다(예: "www.kocca.kr/kocca/...").
    그대로 두면 브라우저에서 상대경로로 오작동할 수 있어, 스킴만 기계적으로
    붙인다(내용을 바꾸거나 지어내는 것이 아니라 형식만 보정).
"""

import sys
import urllib.parse
from pathlib import Path
from typing import List, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import SourceAdapter, StandardProgram, AttachmentRef, ReadinessStatus  # noqa: E402
from common.date_parsing import parse_yyyymmdd  # noqa: E402
from common.env import get_env_value  # noqa: E402

API_URL = "https://kocca.kr/api/pims/List.do"

# 왼쪽은 우리 내부에서 부르는 이름, 오른쪽은 2026-09-07 실제 호출로 확인된
# 진짜 JSON 키 이름이다 (더 이상 추정 아님).
REAL_FIELDS = {
    "id": "intcNoSeq",       # 사업번호
    "title": "title",        # 게시글 제목
    "category": "cate",      # 분류 — 명세서 표의 "cata"는 오타, 실제는 "cate"
    "hit": "hit",             # 조회수
    "reg_date": "regDt",     # 등록일 — 명세서 표의 "regDate"는 오타, 실제는 "regDt"
    "url": "link",           # 게시글 링크 (스킴 없이 옴)
    "start_date": "startDt",  # 접수시작일 (YYYYMMDD)
    "end_date": "endDt",      # 접수마감일 (YYYYMMDD)
    "content": "content",    # 내용
}


class KoccaAdapter(SourceAdapter):
    source_key = "kocca"
    env_var_name = "KOCCA_API_KEY"

    def _get(self, params: dict) -> Optional[dict]:
        readiness = self.check_readiness()
        if readiness != ReadinessStatus.READY:
            self.log_error("http_get", f"호출하지 않음 — 상태: {readiness.value}", {"url": API_URL})
            return None

        api_key = get_env_value(self.env_var_name)

        # .env의 키가 이미 URL 인코딩된 형태(%가 포함됨)라면 requests의
        # params=에 넣지 않는다 — 다시 인코딩되어 이중 인코딩된다(정부24
        # 어댑터에서 실제로 겪은 문제와 동일한 안전장치). 평문 키라면
        # 정상적으로 params=에 넣어도 안전하다.
        try:
            if "%" in api_key:
                query = urllib.parse.urlencode(params)
                full_url = f"{API_URL}?{query}&serviceKey={api_key}"
                response = requests.get(full_url, timeout=10)
            else:
                request_params = dict(params)
                request_params["serviceKey"] = api_key
                response = requests.get(API_URL, params=request_params, timeout=10)
        except requests.exceptions.RequestException as exc:
            safe_message = str(exc).replace(api_key, "****")
            self.log_error("http_get", f"요청 실패: {safe_message}", {"url": API_URL})
            return None

        if response.status_code != 200:
            self.log_error("http_get", f"HTTP {response.status_code}", {"url": API_URL})
            return None

        try:
            return response.json()
        except ValueError:
            self.log_error("http_get", "JSON 파싱 실패", {"url": API_URL})
            return None

    def fetch_list(
        self,
        page: int = 1,
        page_size: int = 10,
        cate: Optional[str] = None,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
    ) -> List[dict]:
        """
        목록 조회. cate는 게시판 카테고리(1:자유공모/2:지정공모/3:모집공고/
        4:종료된 사업), start_dt/end_dt는 YYYYMMDD 형식 — 전부 선택값이라
        지정하지 않으면 기본 목록 전체를 받는다.
        """
        params = {"pageNo": page, "numOfRows": page_size}
        if cate:
            params["cate"] = cate
        if start_dt:
            params["startDt"] = start_dt
        if end_dt:
            params["endDt"] = end_dt

        data = self.fetch_list_response(
            page=page,
            page_size=page_size,
            cate=cate,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        if not data:
            return []

        info = data.get("INFO", {})
        result_code = info.get("resultCode")
        if result_code and result_code != "INFO-000":
            self.log_error(
                "fetch_list",
                f"API 오류 응답: resultCode={result_code}, resultMgs={info.get('resultMgs')}",
                {"url": API_URL},
            )
            return []
        return info.get("list", [])

    def fetch_list_response(
        self,
        page: int = 1,
        page_size: int = 10,
        cate: Optional[str] = None,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
    ) -> Optional[dict]:
        """페이지 메타데이터(listCount)를 포함한 원문 응답을 반환한다."""
        params = {"pageNo": page, "numOfRows": page_size}
        if cate:
            params["cate"] = cate
        if start_dt:
            params["startDt"] = start_dt
        if end_dt:
            params["endDt"] = end_dt
        return self._get(params)

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        f = REAL_FIELDS

        # startDt/endDt는 YYYYMMDD(구분자 없음) 형식으로 온다 — K-Startup과
        # 동일한 형식이라 같은 parse_yyyymmdd()를 쓴다("YYYY-MM-DD ~
        # YYYY-MM-DD"만 해석하는 parse_application_period를 쓰면 이 형식을
        # 못 알아봐서 실제로는 날짜가 있는데도 계속 None이 되는 버그가 난다).
        start_raw = raw_item.get(f["start_date"])
        end_raw = raw_item.get(f["end_date"])
        start = parse_yyyymmdd(start_raw)
        end = parse_yyyymmdd(end_raw)
        if start_raw and end_raw:
            period_raw = f"{start_raw} ~ {end_raw}"
        else:
            period_raw = start_raw or end_raw or None

        raw_link = raw_item.get(f["url"])
        source_url = None
        if raw_link:
            source_url = raw_link if raw_link.startswith("http") else f"https://{raw_link}"

        return StandardProgram(
            source=self.source_key,
            source_program_id=str(raw_item.get(f["id"], "")),
            title=raw_item.get(f["title"], ""),
            organization="한국콘텐츠진흥원",
            application_period_raw=period_raw,
            application_start=start,
            application_end=end,
            target_raw=None,  # 목록 응답에 지원대상 필드 없음 (2026-09-07 실제 호출로 재확인)
            summary_raw=raw_item.get(f["content"]),
            source_url=source_url,
            attachment_urls=[],  # 목록 응답에 첨부파일 필드 없음 (2026-09-07 실제 호출로 재확인)
            collected_at="",  # 호출부(테스트/로더)가 채움
            content_hash="",  # 호출부가 채움
        )

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        # 목록 응답에 첨부파일 관련 필드가 없다 — 항상 빈 리스트.
        return []
