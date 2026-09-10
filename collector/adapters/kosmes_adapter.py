"""중소벤처기업부 기업마당 지원사업 공고 조회 API 어댑터.

공공데이터포털 데이터셋 15157820의 Swagger 명세를 기준으로 구현한다.
서비스는 중소벤처기업부가 제공하지만 KOSMES 출처로 별도 보관한다.
"""

import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import AttachmentRef, ReadinessStatus, SourceAdapter, StandardProgram  # noqa: E402
from common.date_parsing import parse_application_period  # noqa: E402
from common.env import get_env_value  # noqa: E402

API_URL = "https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService"


class KosmesAdapter(SourceAdapter):
    source_key = "kosmes"
    env_var_name = "KOSMES_API_KEY"

    def __init__(self):
        self.last_error = ""

    def _get(self, params: dict) -> Optional[dict]:
        if self.check_readiness() != ReadinessStatus.READY:
            self.last_error = "KOSMES_API_KEY가 없거나 비어 있습니다."
            self.log_error("http_get", self.last_error, {"url": API_URL})
            return None
        key = get_env_value(self.env_var_name)
        request_params = dict(params)
        request_params["serviceKey"] = key
        try:
            if "%" in key:
                encoded = urllib.parse.urlencode({k: v for k, v in request_params.items() if k != "serviceKey"})
                response = requests.get(f"{API_URL}?{encoded}&serviceKey={key}", timeout=20)
            else:
                response = requests.get(API_URL, params=request_params, timeout=20)
        except requests.RequestException as exc:
            self.last_error = "네트워크 요청 실패"
            self.log_error("http_get", str(exc).replace(key, "****"), {"url": API_URL})
            return None
        if response.status_code != 200:
            preview = (response.text or "")[:1000]
            preview_path = Path(__file__).resolve().parent.parent / "logs" / "kosmes_last_error_response.txt"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.write_text(preview, encoding="utf-8")
            self.last_error = f"HTTP {response.status_code} - 응답 내용은 collector/logs/kosmes_last_error_response.txt에서 확인하세요."
            self.log_error("http_get", f"{self.last_error} {preview[:300]}", {"url": API_URL})
            return None
        try:
            payload = response.json()
        except ValueError:
            self.last_error = "JSON 응답 파싱 실패"
            self.log_error("parse_json", self.last_error, {"url": API_URL})
            return None
        # 공공데이터포털 실제 응답은 response.header/body로 한 번 감싸져 온다.
        # 명세 예시처럼 최상위 header/body가 오는 경우도 함께 지원한다.
        if isinstance(payload.get("response"), dict):
            payload = payload["response"]
        result_code = str(payload.get("header", {}).get("resultCode", "00"))
        if result_code not in ("00", "0"):
            self.last_error = f"KOSMES API 오류: {payload.get('header', {}).get('resultMsg', result_code)}"
            self.log_error("api_response", self.last_error, {"url": API_URL})
            return None
        self.last_error = ""
        return payload

    def fetch_response(self, page: int = 1, page_size: int = 10, **filters) -> Optional[dict]:
        params = {"dataType": "json", "pageNo": page, "numOfRows": page_size}
        for name in ("searchLclasId", "hashtags", "pblancId", "registDe", "updtPnttm"):
            if filters.get(name):
                params[name] = filters[name]
        return self._get(params)

    def fetch_list(self, page: int = 1, page_size: int = 10, **filters) -> List[dict]:
        payload = self.fetch_response(page, page_size, **filters)
        if not payload:
            return []
        items = payload.get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        return items

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        period_raw = raw_item.get("reqstBeginEndDe") or ""
        period = parse_application_period(period_raw, datetime.now().date())
        attachments = self.extract_attachments(raw_item)
        return StandardProgram(
            source=self.source_key,
            source_program_id=str(raw_item.get("pblancId") or ""),
            title=raw_item.get("pblancNm") or "",
            organization=raw_item.get("excInsttNm") or raw_item.get("jrsdInsttNm"),
            application_period_raw=period_raw or None,
            application_start=period["start"],
            application_end=period["end"],
            target_raw=raw_item.get("trgetNm"),
            summary_raw=raw_item.get("bsnsSumryCn"),
            source_url=raw_item.get("pblancUrl"),
            attachment_urls=[a.url for a in attachments],
            collected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            content_hash="",
        )

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        names = (raw_item.get("fileNm") or "").split("@")
        urls = (raw_item.get("flpthNm") or "").split("@")
        if not names or not urls or len(names) != len(urls) or names == [""]:
            return []
        return [AttachmentRef(name=name, url=url) for name, url in zip(names, urls) if url]
