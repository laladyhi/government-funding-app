"""
정부24 "대한민국 공공서비스(혜택)" API 어댑터 (일명 보조금24).

이 파일의 요청 URL·파라미터·응답 필드명·인증 방식은 전부 **사용자가
공식 Swagger 명세를 직접 확인해 전달한 값**을 그대로 따른다
(2026-09-04). Claude가 추가로 조사하거나 추정한 부분은 없다. 인증키를
실어보내는 쿼리 파라미터 이름(`serviceKey`)도 공식 Swagger에서 쿼리
인증 파라미터로 명시된 것을 그대로 사용한다(2026-09-07 확인) — 더 이상
관례에 따른 가정이 아니다.

확인된 사실:
  - 목록(serviceList)/상세(serviceDetail)/지원조건(supportConditions)
    3개의 별도 엔드포인트가 있다.
  - 응답 필드명은 전부 한글이다(odcloud.kr 계열 공공데이터 API의 흔한
    방식) — 다른 어댑터(K-Startup 등)처럼 영문 snake_case가 아니다.
  - 지원조건(supportConditions) 응답에는 "JA코드" 계열 값이 포함되는데,
    이 코드가 정확히 무엇을 뜻하는지는 이번 명세만으로 확정할 수 없다.
    그래서 이 어댑터는 지원조건 데이터를 절대 해석/가공하지 않고
    원문 그대로 보존한다 (extract_support_conditions_raw 참고).
  - 첨부파일 URL에 해당하는 필드가 명세에 없다 — attachment_urls는
    항상 빈 리스트로 둔다(임의 생성 금지).

아직 전체 자동 수집은 하지 않는다 — fetch_list()/fetch_detail()/
fetch_support_conditions()는 실제 호출 코드를 담고 있지만, 이 세
메서드를 실제로 실행하는 것은 별도의 테스트 스크립트
(collector/test_public_benefits_api.py, 아직 작성 전)의 몫이며, 이번
작업에서는 fixture로만 변환 로직을 검증한다.
"""

import sys
import urllib.parse
from pathlib import Path
from typing import List, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import SourceAdapter, StandardProgram, AttachmentRef, ReadinessStatus  # noqa: E402
from common.date_parsing import parse_application_period  # noqa: E402
from common.env import get_env_value  # noqa: E402

from datetime import date

BASE_URL = "https://api.odcloud.kr/api"
LIST_URL = f"{BASE_URL}/gov24/v3/serviceList"
DETAIL_URL = f"{BASE_URL}/gov24/v3/serviceDetail"
CONDITIONS_URL = f"{BASE_URL}/gov24/v3/supportConditions"

# 공식 Swagger 명세에서 쿼리 인증 파라미터로 확인됨(2026-09-07, 사용자 확인).
SERVICE_KEY_PARAM = "serviceKey"

# 사용자가 확인한 실제 응답 필드명 (전부 한글) -> 내부에서 부르는 이름
FIELDS = {
    "id": "서비스ID",
    "support_type": "지원유형",
    "title": "서비스명",
    "purpose_summary": "서비스목적요약",
    "purpose": "서비스목적",
    "target": "지원대상",
    "selection_criteria": "선정기준",
    "support_content": "지원내용",
    "apply_method": "신청방법",
    "apply_deadline": "신청기한",
    "detail_url": "상세조회URL",
    "online_apply_url": "온라인신청사이트URL",
    "organization": "소관기관명",
    "user_type": "사용자구분",
    "service_field": "서비스분야",
    "modified_at": "수정일시",
}

# 2026-09-07 실제 호출로 확인됨: 목록(serviceList)과 상세(serviceDetail)
# 응답이 "접수기관"/"문의" 항목에 서로 다른 필드명을 쓴다. 하나의
# raw_item이 목록에서 왔는지 상세에서 왔는지 구분하지 않고도 맞는
# 값을 찾을 수 있도록, to_standard_program에서는 두 이름을 순서대로
# 조회한다(FIELDS 딕셔너리 하나로는 표현이 안 돼서 별도로 둔다).
RECEIVING_ORG_KEYS = ("접수기관", "접수기관명")   # 목록 / 상세
CONTACT_KEYS = ("전화문의", "문의처")             # 목록 / 상세


def _first_present(raw_item: dict, keys: tuple) -> Optional[str]:
    for key in keys:
        value = raw_item.get(key)
        if value:
            return value
    return None


class PublicBenefitsAdapter(SourceAdapter):
    source_key = "public_benefits"
    env_var_name = "PUBLIC_BENEFITS_API_KEY"

    # ── 실제 호출 (check_readiness()가 READY일 때만 의미 있음) ──────────

    def _get(self, url: str, params: dict) -> Optional[dict]:
        """
        공통 GET 호출. 키가 없으면 절대 호출하지 않는다. 오류/키 값은
        로그에도, 반환값에도 남기지 않는다(마스킹).

        중요: .env의 서비스키는 공공데이터포털이 발급한 "Encoding" 형태
        (예: %2B, %3D%3D 포함)로 이미 URL 인코딩되어 있다. requests의
        params=에 그대로 넣으면 requests가 값을 다시 인코딩해버려
        %2B가 %252B로 깨진다(이중 인코딩) — 이러면 서버가 다른 키로
        인식해 401을 반환한다(2026-09-07 실제 호출로 확인된 버그).
        그래서 나머지 파라미터는 urlencode로 정상 인코딩하고, 서비스키만
        이미 인코딩된 문자열 그대로 쿼리스트링 끝에 직접 붙인다 —
        K-Startup 테스트 스크립트(collector/test_kstartup_api.py)에서
        쓴 것과 같은 방식이다.
        """
        readiness = self.check_readiness()
        if readiness != ReadinessStatus.READY:
            self.log_error("http_get", f"호출하지 않음 — 상태: {readiness.value}", {"url": url})
            return None

        api_key = get_env_value(self.env_var_name)
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}&{SERVICE_KEY_PARAM}={api_key}"
        try:
            response = requests.get(full_url, timeout=10)
        except requests.exceptions.RequestException as exc:
            # 예외 메시지에 URL 전체(키 포함)가 들어갈 수 있어 마스킹한다.
            safe_message = str(exc).replace(api_key, "****")
            self.log_error("http_get", f"요청 실패: {safe_message}", {"url": url})
            return None

        if response.status_code != 200:
            self.log_error("http_get", f"HTTP {response.status_code}", {"url": url})
            return None

        try:
            return response.json()
        except ValueError:
            self.log_error("http_get", "JSON 파싱 실패", {"url": url})
            return None

    def fetch_list(self, page: int = 1, page_size: int = 10, cond: Optional[dict] = None) -> List[dict]:
        """
        목록 조회 (serviceList). cond는 이미 완성된 파라미터 키를
        그대로 받는다 — 예: {"cond[서비스명::LIKE]": "창업"}.
        전체 자동 수집을 막기 위해, 호출하는 쪽에서 page_size를 반드시
        5 이하로 제한해서 쓰는 것을 권장한다 (강제하지는 않음 — 강제는
        실행 스크립트/테스트 쪽 책임).
        """
        params = {"page": page, "perPage": page_size, "returnType": "JSON"}
        if cond:
            params.update(cond)
        data = self._get(LIST_URL, params)
        if not data:
            return []
        return data.get("data", [])

    def fetch_detail(self, service_id: str) -> Optional[dict]:
        """상세 조회 (serviceDetail) — 서비스ID 하나에 대한 상세 레코드."""
        params = {
            "page": 1,
            "perPage": 1,
            "returnType": "JSON",
            "cond[서비스ID::EQ]": service_id,
        }
        data = self._get(DETAIL_URL, params)
        if not data:
            return None
        items = data.get("data", [])
        return items[0] if items else None

    def fetch_support_conditions_raw(self, service_id: str) -> list:
        """
        지원조건 조회 (supportConditions). JA코드 등 값의 의미를 이
        어댑터가 해석하지 않는다 — 받은 그대로 반환한다. 호출부는 이
        결과를 그대로 보존만 하고, 사람이 읽을 문구로 가공하려면 별도
        확인(정부24 코드표) 후 처리해야 한다.
        """
        params = {
            "page": 1,
            "perPage": 100,
            "returnType": "JSON",
            "cond[서비스ID::EQ]": service_id,
        }
        data = self._get(CONDITIONS_URL, params)
        if not data:
            return []
        return data.get("data", [])

    # ── 순수 변환 (네트워크 호출 없음) ──────────────────────────────────

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        f = FIELDS

        period_raw = raw_item.get(f["apply_deadline"])
        period = parse_application_period(period_raw or "", date.today())
        # parse_application_period는 'YYYY-MM-DD ~ YYYY-MM-DD' 형태만
        # 해석한다. 그 외 형태(예: '상시', 단일 날짜 등)는 원문만
        # 보존하고 start/end는 None으로 둔다 — 억지로 만들지 않는다.

        organization = raw_item.get(f["organization"]) or None

        target_parts = [raw_item.get(f["target"]), raw_item.get(f["selection_criteria"])]
        target_raw = " / ".join(p for p in target_parts if p) or None
        user_type = raw_item.get(f["user_type"])
        if user_type and target_raw:
            target_raw = f"[대상구분: {user_type}] {target_raw}"
        elif user_type:
            target_raw = f"[대상구분: {user_type}]"

        summary_parts = [
            raw_item.get(f["purpose_summary"]) or raw_item.get(f["purpose"]),
            raw_item.get(f["support_content"]),
        ]
        summary_raw = " / ".join(p for p in summary_parts if p) or None

        return StandardProgram(
            source=self.source_key,
            source_program_id=str(raw_item.get(f["id"], "")),
            title=raw_item.get(f["title"], ""),
            organization=organization,
            application_period_raw=period_raw,
            application_start=period["start"],
            application_end=period["end"],
            target_raw=target_raw,
            summary_raw=summary_raw,
            source_url=raw_item.get(f["detail_url"]),
            attachment_urls=[],  # 명세에 첨부파일 필드 없음 — 임의 생성 금지
            collected_at="",  # 호출부(테스트/로더)가 채움
            content_hash="",  # 호출부가 채움
        )

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        # 명세에 첨부파일 관련 필드가 없다 — 항상 빈 리스트.
        return []
