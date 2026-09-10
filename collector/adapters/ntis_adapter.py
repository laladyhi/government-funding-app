"""NTIS 국가R&D 과제검색(전체용) API 어댑터.

공식 매뉴얼(01.통합OpenAPI_국가R&D 과제검색(전체용)_매뉴얼_2025.pdf)의
public_project REST/XML 명세를 기준으로 구현한다.
"""

import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.base import ReadinessStatus, SourceAdapter, StandardProgram  # noqa: E402
from common.date_parsing import parse_yyyymmdd  # noqa: E402
from common.env import get_env_value  # noqa: E402

API_URL = "https://www.ntis.go.kr/rndopen/openApi/public_project"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> List[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag).lower() == name.lower()]


def _first_text(element: ET.Element, *path: str) -> Optional[str]:
    current = [element]
    for name in path:
        next_nodes = []
        for node in current:
            next_nodes.extend(_children(node, name))
        current = next_nodes
        if not current:
            return None
    value = (current[0].text or "").strip()
    return value or None


class NtisAdapter(SourceAdapter):
    source_key = "ntis"
    env_var_name = "NTIS_API_KEY"

    def __init__(self):
        self.last_error = ""

    def _get_xml(self, params: dict) -> Optional[str]:
        readiness = self.check_readiness()
        if readiness != ReadinessStatus.READY:
            self.log_error("http_get", f"호출하지 않음 — 상태: {readiness.value}", {"url": API_URL})
            return None
        key = get_env_value(self.env_var_name)
        try:
            # 승인키가 이미 URL 인코딩되어 있어도 이중 인코딩하지 않는다.
            request_params = dict(params)
            request_params.pop("apprvKey", None)
            if "%" in key:
                query = urllib.parse.urlencode(request_params)
                response = requests.get(f"{API_URL}?{query}&apprvKey={key}", timeout=20)
            else:
                request_params["apprvKey"] = key
                response = requests.get(API_URL, params=request_params, timeout=20)
        except requests.RequestException as exc:
            self.last_error = "네트워크 요청 실패"
            self.log_error("http_get", str(exc).replace(key, "****"), {"url": API_URL})
            return None
        if response.status_code != 200:
            self.last_error = f"HTTP {response.status_code}"
            self.log_error("http_get", f"HTTP {response.status_code}", {"url": API_URL})
            return None
        self.last_error = ""
        return response.text

    def fetch_response(
        self,
        keyword: str,
        start_position: int = 1,
        display_count: int = 10,
        search_field: str = "BI",
        add_query: Optional[str] = None,
        search_rank: str = "RANK/DESC",
    ) -> Optional[str]:
        params = {
            "apprvKey": "",  # _get_xml에서 실제 승인키를 안전하게 주입한다.
            "query": keyword,
            "userId": "",
            "collection": "project",
            "searchField": search_field,
            "displayCount": display_count,
            "startPosition": start_position,
            "naviCount": 30,
            "sortby": search_rank,
            "boostquery": "",
            "addQuery": add_query or "",
        }
        return self._get_xml(params)

    def fetch_list(
        self,
        keyword: str,
        start_position: int = 1,
        display_count: int = 10,
        search_field: str = "BI",
        add_query: Optional[str] = None,
    ) -> List[dict]:
        xml_text = self.fetch_response(keyword, start_position, display_count, search_field, add_query)
        if not xml_text:
            return []
        return self.parse_items(xml_text)

    def parse_items(self, xml_text: str) -> List[dict]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            self.last_error = "XML 파싱 실패"
            self.log_error("parse_xml", str(exc), {"url": API_URL})
            return []
        if _local_name(root.tag).lower() == "error":
            message = (root.text or "").strip()
            self.last_error = f"NTIS 오류: {message or '알 수 없는 오류'}"
            return []
        items = [self._hit_to_dict(hit) for hit in root.iter() if _local_name(hit.tag).upper() == "HIT"]
        if not items:
            self.last_error = f"과제 항목 없음 (root={_local_name(root.tag)})"
        return items

    def _hit_to_dict(self, hit: ET.Element) -> dict:
        return {
            "project_number": _first_text(hit, "ProjectNumber"),
            "title": _first_text(hit, "ProjectTitle", "Korean"),
            "manager": _first_text(hit, "Manager", "Name"),
            "research_agency": _first_text(hit, "ResearchAgency", "Name"),
            "ministry": _first_text(hit, "Ministry", "Name"),
            "project_year": _first_text(hit, "ProjectYear"),
            "start": _first_text(hit, "ProjectPeriod", "Start"),
            "end": _first_text(hit, "ProjectPeriod", "End"),
            "total_start": _first_text(hit, "ProjectPeriod", "TotalStart"),
            "total_end": _first_text(hit, "ProjectPeriod", "TotalEnd"),
            "goal": _first_text(hit, "Goal", "Full") or _first_text(hit, "Goal", "Teaser"),
            "abstract": _first_text(hit, "Abstract", "Full") or _first_text(hit, "Abstract", "Teaser"),
            "effect": _first_text(hit, "Effect", "Full") or _first_text(hit, "Effect", "Teaser"),
            "keyword_ko": _first_text(hit, "Keyword", "Korean"),
            "government_funds": _first_text(hit, "GovernmentFunds"),
            "total_funds": _first_text(hit, "TotalFunds"),
            "corporate_registration_number": _first_text(hit, "CorporateRegistrationNumber"),
            "raw_xml": ET.tostring(hit, encoding="unicode"),
        }

    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        start_raw = raw_item.get("start") or raw_item.get("total_start")
        end_raw = raw_item.get("end") or raw_item.get("total_end")
        start = parse_yyyymmdd(start_raw) if start_raw else None
        end = parse_yyyymmdd(end_raw) if end_raw else None
        period = f"{start_raw} ~ {end_raw}" if start_raw and end_raw else start_raw or end_raw
        summary_parts = [raw_item.get("goal"), raw_item.get("abstract"), raw_item.get("effect")]
        summary = "\n".join(part for part in summary_parts if part) or None
        project_id = str(raw_item.get("project_number") or "")
        return StandardProgram(
            source=self.source_key,
            source_program_id=project_id,
            title=raw_item.get("title") or "",
            organization=raw_item.get("research_agency") or raw_item.get("manager"),
            application_period_raw=period,
            application_start=start,
            application_end=end,
            target_raw=None,
            summary_raw=summary,
            source_url=f"https://www.ntis.go.kr/project/pjtInfo.do?pjtId={project_id}" if project_id else None,
            attachment_urls=[],
            collected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            content_hash="",
        )
