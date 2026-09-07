"""
창업진흥원 K-Startup 어댑터 — "지원사업 공고 정보"(getAnnouncementInformation01)
공공데이터포털 Open API 대상.

2026-09-04 실제 API 테스트(collector/test_kstartup_api.py, perPage=5)로
아래 필드명을 직접 확인했다. 더 이상 추정값(ASSUMED_FIELDS)이 아니다.
근거 문서: [가이드]창업진흥원_K-Startup(...)_250108/서비스설계서_v2.0.docx
(표 7~9, "2) [지원사업 공고 정보] 상세기능명세"), 실제 응답:
collector/fixtures/kstartup_real_sample_20260904.json

확인된 사실:
  - 최상위 응답의 `id`는 그 페이지 안에서의 순번(1,2,3,...)일 뿐이다.
    공고를 식별하는 진짜 고유값은 `pbanc_sn`이다. `id`를 공고 ID로 쓰면
    안 된다.
  - 날짜(`pbanc_rcpt_bgng_dt`/`pbanc_rcpt_end_dt`)는 'YYYYMMDD' 형식
    (구분자 없음)이다. 가이드 문서의 응답 예제는 'YYYY-MM-DD HH:MM:SS'
    형식으로 나와 있었지만 실제 응답은 달랐다 — 실제 응답 기준으로
    파싱한다 (collector/common/date_parsing.py의 parse_yyyymmdd 사용).
  - 응답에 첨부파일 URL 필드가 없다 (28개 필드 전수 확인). 임의로
    만들어내지 않는다 — attachment_urls는 항상 빈 리스트.
  - `sprv_inst`(주관기관)는 실제 기관명이 아니라 "공공기관", "민간" 같은
    유형 표현으로 오는 경우가 많다. 이런 값은 기관명으로 저장하지 않고
    None(= 기관명 미확인)으로 둔다.

아직 전체 자동 수집은 하지 않는다 — fetch_list()는 여전히 호출을
막아뒀고, 이번엔 실제 캡처된 5건(fixture)만으로 변환을 검증한다.
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import SourceAdapter, StandardProgram, AttachmentRef, ReadinessStatus  # noqa: E402
from common.date_parsing import parse_yyyymmdd  # noqa: E402

# 가이드 문서 표7 "Call Back URL(외부노출URL)" — 2026-09-04 실제 호출로 확인됨
API_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"

# 실제 응답에서 확인된 필드명 (더 이상 추정 아님)
REAL_FIELDS = {
    "id": "pbanc_sn",              # 공고 고유 ID (주의: 최상위 'id'는 페이지 내 순번 — 쓰지 않음)
    "title": "biz_pbanc_nm",       # 사업명
    "organization": "sprv_inst",   # 주관기관 (값이 "공공기관"/"민간"처럼 일반 표현일 수 있음)
    "start_date": "pbanc_rcpt_bgng_dt",  # 신청 시작일 (YYYYMMDD)
    "end_date": "pbanc_rcpt_end_dt",     # 신청 마감일 (YYYYMMDD)
    "target": "aply_trgt",         # 지원 대상
    "target_detail": "aply_trgt_ctnt",   # 지원 대상 상세설명
    "content": "pbanc_ctnt",       # 공고 내용
    "url": "detl_pg_url",          # 상세 URL
}

# sprv_inst에 실제로 특정 기관을 가리키지 않는 일반 유형 표현이 들어오는
# 경우 — 이런 값은 기관명으로 저장하지 않는다.
GENERIC_ORG_TERMS = {"공공기관", "민간", "기타"}


class KstartupAdapter(SourceAdapter):
    source_key = "kstartup"
    env_var_name = "KSTARTUP_API_KEY"

    def fetch_list(self, page: int = 1, page_size: int = 10) -> List[dict]:
        """
        실제 엔드포인트/인증 방식은 확인됐지만(collector/test_kstartup_api.py
        참고), 여기서는 여전히 실제 대량 호출을 수행하지 않는다 — 전체
        자동 수집은 별도 승인 후 진행한다.
        """
        readiness = self.check_readiness()
        if readiness != ReadinessStatus.READY:
            self.log_error("fetch_list", f"호출하지 않음 — 상태: {readiness.value}")
            return []

        self.log_error(
            "fetch_list",
            "전체 자동 수집은 아직 승인되지 않아 호출하지 않습니다. "
            "필요하면 collector/test_kstartup_api.py 방식을 참고해 "
            "명시적으로 승인받은 뒤에만 호출하세요.",
        )
        return []

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        f = REAL_FIELDS

        start_raw = raw_item.get(f["start_date"])
        end_raw = raw_item.get(f["end_date"])
        start = parse_yyyymmdd(start_raw)
        end = parse_yyyymmdd(end_raw)
        if start_raw and end_raw:
            period_raw = f"{start_raw} ~ {end_raw}"
        else:
            period_raw = start_raw or end_raw or None

        org_raw = raw_item.get(f["organization"])
        organization = None if (not org_raw or org_raw in GENERIC_ORG_TERMS) else org_raw

        target_main = raw_item.get(f["target"])
        target_detail = raw_item.get(f["target_detail"])
        target_parts = [p for p in (target_main, target_detail) if p]
        target_raw = " / ".join(target_parts) if target_parts else None

        return StandardProgram(
            source=self.source_key,
            source_program_id=str(raw_item.get(f["id"], "")),
            title=raw_item.get(f["title"], ""),
            organization=organization,
            application_period_raw=period_raw,
            application_start=start,
            application_end=end,
            target_raw=target_raw,
            summary_raw=raw_item.get(f["content"]),
            source_url=raw_item.get(f["url"]),
            attachment_urls=[],  # 확인됨: 응답에 첨부파일 필드 없음 (임의 생성 금지)
            collected_at="",  # 호출부(테스트/로더)가 채움
            content_hash="",  # 호출부가 채움
        )

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        # 확인됨: getAnnouncementInformation01 응답에는 첨부파일 URL이 없다.
        return []
