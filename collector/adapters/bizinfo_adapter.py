"""
기업마당 어댑터 — 공통 인터페이스(SourceAdapter)를 지키기 위한 얇은 래퍼.

중요: 기업마당의 실제 운영 파이프라인은 지금도 collector/fetch_and_store.py
+ app/db/load_bizinfo.py 그대로다. 이 파일은 그 파이프라인을 대체하지
않는다 — 앞으로 "등록된 모든 출처를 같은 방식으로 순회"하는 코드를 짤 때
기업마당도 같은 인터페이스로 다룰 수 있도록 맞춰둔 껍데기일 뿐이다.

그래서 이 어댑터의 to_standard_program()이 계산하는 content_hash는
raw-data-hash-policy.md의 "파일 바이트 기준" 해시가 아니라, 이 어댑터
내부에서만 쓰는 별도의 데모용 해시다 (파일 I/O 없이 순수 변환만 하기
위함). 실제 DB에 저장되는 기업마당 데이터의 해시는 여전히
compute_file_hash()가 유일한 기준이다.
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import SourceAdapter, StandardProgram, AttachmentRef  # noqa: E402
from common.date_parsing import parse_application_period  # noqa: E402


class BizinfoAdapter(SourceAdapter):
    source_key = "bizinfo"
    env_var_name = "BIZINFO_API_KEY"

    def fetch_list(self, page: int = 1, page_size: int = 10) -> List[dict]:
        """
        실제 목록 조회는 여전히 collector/fetch_and_store.py의 fetch_page()가
        담당한다. 여기서는 순환 의존을 피하고 기존 파이프라인을 건드리지
        않기 위해 일부러 호출하지 않는다 — 인터페이스 형태만 맞춰둔다.
        """
        self.log_error(
            "fetch_list",
            "BizinfoAdapter.fetch_list()는 데모용입니다. 실제 수집은 "
            "collector/fetch_and_store.py를 그대로 사용하세요.",
        )
        return []

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        period = parse_application_period(
            raw_item.get("reqstBeginEndDe", ""), datetime.now().date()
        )
        attachments = []
        file_names = raw_item.get("fileNm", "")
        file_urls = raw_item.get("flpthNm", "")
        if file_names and file_urls:
            names, urls = file_names.split("@"), file_urls.split("@")
            if len(names) == len(urls):
                attachments = urls

        canonical = json.dumps(raw_item, ensure_ascii=False, sort_keys=True)
        demo_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return StandardProgram(
            source=self.source_key,
            source_program_id=raw_item.get("pblancId", ""),
            title=raw_item.get("pblancNm", ""),
            organization=raw_item.get("excInsttNm"),
            application_period_raw=raw_item.get("reqstBeginEndDe"),
            application_start=period["start"],
            application_end=period["end"],
            target_raw=raw_item.get("trgetNm"),
            summary_raw=raw_item.get("bsnsSumryCn"),
            source_url=raw_item.get("pblancUrl"),
            attachment_urls=attachments,
            collected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            content_hash=demo_hash,
        )

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        names = (raw_item.get("fileNm") or "").split("@")
        urls = (raw_item.get("flpthNm") or "").split("@")
        if not names or not urls or len(names) != len(urls) or names == [""]:
            return []
        return [AttachmentRef(name=n, url=u) for n, u in zip(names, urls)]
