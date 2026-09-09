"""e나라도움·보조금통합포털 국고보조금 공모사업 API 어댑터.

근거: 사용자가 제공한 공식 API 주소와 실제 XML 응답 샘플
T_OPD_ASBS_PBNS_UNITY.xml / T_OPD_ASBS_UNITY.xml.
"""

import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import ReadinessStatus, SourceAdapter, StandardProgram, AttachmentRef  # noqa: E402
from common.date_parsing import parse_application_period, parse_yyyymmdd  # noqa: E402
from common.env import get_env_value  # noqa: E402

BASE_URL = "https://apis.data.go.kr/1051000/MoefOpenAPI2025"
PBNS_UNITY_URL = f"{BASE_URL}/T_OPD_ASBS_PBNS_UNITY"
ASBS_UNITY_URL = f"{BASE_URL}/T_OPD_ASBS_UNITY"
SERVICE_KEY_PARAM = "serviceKey"

FIELDS = {
    "id": "DTLBZ_ID",
    "title": "PBLANC_NM",
    "organization": "JRSD_NM",
    "target": "SPORT_TRGET_CN",
    "excluded": "EXCL_TRGET_CN",
    "purpose": "DTLBZ_BSNS_PURPS_DC",
    "support_content": "SPORT_CN_DC",
    "apply_method": "REQST_RCEPT_MTH_CN",
    "selection": "SLCTN_STDR_DC",
    "start_date": "PBLANC_BEGIN_DE",
    "end_date": "PBLANC_END_DE",
    "business_start": "BSNS_BEGIN_DE",
    "business_end": "BSNS_END_DE",
    "amount": "GOVSUBY",
    "support_amount": "SPORT_BGAMT",
    "total_amount": "TGYL_YEAR_BSNS_AMOUNT",
    "region": "CTPRVN_NM",
    "url": "PBLANC_POPUP_URL",
    "business_url": "BSNS_POPUP_URL",
}


def _clean(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    text = text.replace("<![CDATA[", "").replace("]]>", "").strip()
    return text or None


def _parse_xml(text: str) -> dict:
    root = ET.fromstring(text)
    header = {child.tag: _clean(child.text) for child in root.find("header") or []}
    body_node = root.find("body")
    body = {}
    if body_node is not None:
        for child in body_node:
            if child.tag == "items":
                body["items"] = [
                    {field.tag: _clean(field.text) for field in item}
                    for item in child.findall("item")
                ]
            else:
                body[child.tag] = _clean(child.text)
    return {"header": header, "body": body}


def _response_body(data: dict) -> dict:
    response = data.get("response")
    if isinstance(response, dict):
        return response.get("body") or response
    return data.get("body") or data


def _response_header(data: dict) -> dict:
    """JSON/XML 공통 형태로 정규화된 응답에서 header를 가져온다."""
    response = data.get("response")
    if isinstance(response, dict):
        return response.get("header") or {}
    return data.get("header") or {}


def _json_to_items(data: dict) -> list:
    body = _response_body(data)
    items = body.get("items") if isinstance(body, dict) else []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else []


def _date_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    compact = re.sub(r"[^0-9]", "", value)
    return parse_yyyymmdd(compact) if len(compact) == 8 else None


class EnaraAdapter(SourceAdapter):
    source_key = "enara"
    env_var_name = "ENARA_API_KEY"

    def __init__(self):
        self.last_error = None

    def _get(self, url: str, params: dict) -> Optional[dict]:
        self.last_error = None
        readiness = self.check_readiness()
        if readiness != ReadinessStatus.READY:
            self.log_error("http_get", f"호출하지 않음 — 상태: {readiness.value}", {"url": url})
            return None
        api_key = get_env_value(self.env_var_name)
        query = urllib.parse.urlencode(params)
        if "%" in api_key:
            full_url = f"{url}?{query}&{SERVICE_KEY_PARAM}={api_key}"
            request_kwargs = {"url": full_url}
        else:
            request_kwargs = {"url": url, "params": {**params, SERVICE_KEY_PARAM: api_key}}
        # 197,936건 규모(198페이지) 전체 수집처럼 오래 걸리는 실행에서는
        # 순간적인 네트워크 타임아웃 한 번 때문에 지금까지 받은 페이지를
        # 전부 버리고 처음부터 다시 받아야 하는 게 너무 비싸다(2026-09-09
        # 페이지 171에서 connect timeout으로 전체 실행이 중단된 사례).
        # 연결/타임아웃류 오류만 최대 2회 재시도한다 — 응답을 받았지만
        # 내용이 이상한 경우(HTTP 4xx/5xx, JSON 파싱 실패 등)는 재시도해도
        # 소용없으므로 그대로 실패 처리한다.
        response = None
        last_exc = None
        for attempt in range(3):
            try:
                response = requests.get(timeout=20, **request_kwargs)
                response.raise_for_status()
                last_exc = None
                break
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        if last_exc is not None:
            safe_error = str(last_exc).replace(api_key, "****")
            self.last_error = f"외부 API 접속 실패(재시도 3회 모두 실패): {safe_error}"
            self.log_error("http_get", safe_error, {"url": url})
            return None
        if response.status_code != 200:
            self.last_error = f"API가 HTTP {response.status_code}를 반환했습니다."
            self.log_error("http_get", self.last_error, {"url": url})
            return None
        try:
            if "json" in response.headers.get("Content-Type", "").lower() or response.text.lstrip().startswith("{"):
                return response.json()
            return _parse_xml(response.text)
        except (ValueError, ET.ParseError):
            self.last_error = "API 응답을 JSON/XML로 해석하지 못했습니다."
            self.log_error("http_get", "JSON/XML 응답 해석 실패", {"url": url})
            return None

    def fetch_list_response(
        self,
        page: int = 1,
        page_size: int = 5,
        operation: str = "PBNS_UNITY",
        business_year: Optional[int] = None,
    ) -> Optional[dict]:
        url = PBNS_UNITY_URL if operation == "PBNS_UNITY" else ASBS_UNITY_URL
        # 공식 명세상 resultType과 bsnsyear는 필수 요청변수다.
        # resultType은 JSON으로 통일해 응답 필드 확인을 쉽게 한다.
        params = {
            "pageNo": page,
            "numOfRows": page_size,
            "resultType": "json",
            "bsnsyear": str(business_year or datetime.now().year),
        }
        return self._get(url, params)

    def fetch_list(
        self,
        page: int = 1,
        page_size: int = 5,
        business_year: Optional[int] = None,
    ) -> List[dict]:
        response = self.fetch_list_response(page, page_size, business_year=business_year)
        if not response:
            return []
        return _json_to_items(response)

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        f = FIELDS
        start_raw = _clean(raw_item.get(f["start_date"])) or _clean(raw_item.get(f["business_start"]))
        end_raw = _clean(raw_item.get(f["end_date"])) or _clean(raw_item.get(f["business_end"]))
        start = _date_value(start_raw)
        end = _date_value(end_raw)
        period_raw = f"{start_raw} ~ {end_raw}" if start_raw and end_raw else start_raw or end_raw
        target = _clean(raw_item.get(f["target"]))
        selection = _clean(raw_item.get(f["selection"]))
        target_raw = " / ".join(value for value in (target, selection) if value) or None
        summary = " / ".join(
            value for value in (_clean(raw_item.get(f["purpose"])), _clean(raw_item.get(f["support_content"]))) if value
        ) or None
        url = _clean(raw_item.get(f["url"])) or _clean(raw_item.get(f["business_url"]))
        return StandardProgram(
            source=self.source_key,
            source_program_id=_clean(raw_item.get(f["id"])) or "",
            title=_clean(raw_item.get(f["title"])) or _clean(raw_item.get("DTLBZ_NM")) or "",
            organization=_clean(raw_item.get(f["organization"])),
            application_period_raw=period_raw,
            application_start=start,
            application_end=end,
            target_raw=target_raw,
            summary_raw=summary,
            source_url=url,
            attachment_urls=[],
            collected_at="",
            content_hash="",
        )

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        return []


def extract_items(response: dict) -> list:
    return _json_to_items(response)


def extract_total_count(response: dict) -> int:
    body = _response_body(response)
    try:
        return int(body.get("totalCount") or 0)
    except (TypeError, ValueError):
        return 0


def extract_response_code(response: dict) -> str:
    return str(_response_header(response).get("resultCode") or "")


def extract_response_message(response: dict) -> str:
    return str(_response_header(response).get("resultMsg") or "")
