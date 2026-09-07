"""
한국콘텐츠진흥원(KOCCA) 어댑터 — 공공데이터포털 Open API
(data.go.kr/data/15134251, "한국콘텐츠진흥원_지원사업공고") 대상.

⚠️ 실제 API 미검증 상태 (2026-09-04 기준)
이 어댑터의 필드명(ASSUMED_FIELDS)은 실제 응답을 한 번도 받아보지 못한
채, 조사 단계 요약(docs/kocca-adapter-feasibility.md)만 보고 "이런
이름일 것"이라고 추정한 값이다. 요청 URL도 마찬가지로 확정되지 않았다.
서비스키가 운영단계 심의승인을 받아 실제 호출이 가능해지면, **반드시**
실제 응답을 한 번 받아서 이 파일의 ASSUMED_FIELDS와 API_URL을 실제
값으로 고친 뒤 사용해야 한다. 그 전까지 fetch_list()는 의도적으로
막혀 있다.

지금 이 어댑터를 테스트하려면 collector/fixtures/kocca_sample_response.json
(가상 데이터)을 쓰는 test_standard_source_pipeline.py를 실행한다 —
실제 API는 호출하지 않는다.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import SourceAdapter, StandardProgram, AttachmentRef, ReadinessStatus  # noqa: E402
from common.date_parsing import parse_application_period  # noqa: E402

# 요청 URL: 공공데이터포털에서 서비스키 승인 후 "API 문서" 탭에서
# 정확한 값으로 반드시 교체할 것. 지금은 확정되지 않았다.
API_URL = None  # TODO(승인 후): 실제 요청 URL로 교체

# 실제 응답 필드명이 확정되지 않아, 조사 요약 문구를 바탕으로 "추정"한
# 이름이다. 왼쪽은 우리 내부에서 부르는 이름, 오른쪽은 KOCCA가 실제로
# 쓸 것으로 "짐작"한 JSON 키 이름 — 반드시 실제 응답과 대조할 것.
ASSUMED_FIELDS = {
    "id": "pblancNo",          # 사업번호 (추정)
    "title": "pblancTitle",    # 게시물제목 (추정)
    "category": "category",    # 분류 (추정)
    "reg_date": "regDate",     # 등록일 (추정)
    "url": "pblancUrl",        # 게시글 링크 (추정)
    "start_date": "rcptStartDate",  # 접수시작일 (추정)
    "end_date": "rcptEndDate",      # 접수마감일 (추정)
    "content": "content",      # 내용 (추정)
}


class KoccaAdapter(SourceAdapter):
    source_key = "kocca"
    env_var_name = "KOCCA_API_KEY"

    def fetch_list(self, page: int = 1, page_size: int = 10) -> List[dict]:
        readiness = self.check_readiness()
        if readiness != ReadinessStatus.READY:
            self.log_error("fetch_list", f"호출하지 않음 — 상태: {readiness.value}")
            return []

        # 키가 있어도, 요청 URL이 아직 확정되지 않았으므로 실제 호출을
        # 의도적으로 막는다. 이건 버그가 아니라 안전장치다.
        if API_URL is None:
            self.log_error(
                "fetch_list",
                "API_URL이 아직 확정되지 않아 실제 호출을 하지 않습니다. "
                "공공데이터포털 승인 후 API 문서를 확인하고 이 파일을 "
                "수정하세요.",
            )
            return []

        raise NotImplementedError(
            "API_URL이 채워지면 여기에 requests.get(...) 호출을 추가하세요. "
            "그 전까지는 절대 이 지점에 도달하지 않습니다."
        )

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        """
        raw_item은 ASSUMED_FIELDS 이름을 따른다고 "가정"한다. 실제 응답의
        키 이름이 다르면 이 함수가 조용히 빈 값만 채우게 되므로, 실제 키를
        확인하면 ASSUMED_FIELDS와 이 함수를 함께 고쳐야 한다.
        """
        f = ASSUMED_FIELDS
        start_raw = raw_item.get(f["start_date"])
        end_raw = raw_item.get(f["end_date"])
        period_raw = f"{start_raw} ~ {end_raw}" if start_raw and end_raw else None
        period = parse_application_period(period_raw or "", datetime.now().date())

        return StandardProgram(
            source=self.source_key,
            source_program_id=str(raw_item.get(f["id"], "")),
            title=raw_item.get(f["title"], ""),
            organization="한국콘텐츠진흥원",
            application_period_raw=period_raw,
            application_start=period["start"],
            application_end=period["end"],
            target_raw=None,  # 목록 응답에 지원대상 필드가 있는지 자체가 미확인
            summary_raw=raw_item.get(f["content"]),
            source_url=raw_item.get(f["url"]),
            attachment_urls=[],  # 첨부파일 제공 여부 미확인 (kocca-adapter-feasibility.md 참고)
            collected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            content_hash="",  # 로더가 표준 방식으로 계산해 채움
        )

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        # 첨부파일이 API 응답에 포함되는지 자체가 미확인 상태
        # (docs/kocca-adapter-feasibility.md "보류·유의 사항" 참고).
        return []
