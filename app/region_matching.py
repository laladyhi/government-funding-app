"""지역 필터를 위한 저장 데이터 기반 보조 함수."""

import html
import json
import re


_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_REGION_KEYS = {
    "CTPRVN_NM",  # 시·도
    "SIGNGU_NM",  # 시·군·구
    "DLVPL_NM",   # 사업 수행/배분 지역
    "region",
    "region_display",
}
_NATIONWIDE_MARKERS = (
    "전국",
    "전국공통",
    "전국 단위",
    "지역 제한 없음",
    "지역제한없음",
    "제한 없음",
    "제한없음",
)


def clean_region_text(value) -> str:
    """CDATA와 HTML 엔티티를 제거해 사람이 읽는 지역명으로 정리한다."""
    if value is None:
        return ""
    text = html.unescape(str(value)).strip()
    while _CDATA_RE.search(text):
        text = _CDATA_RE.sub(r"\1", text)
    return " ".join(text.split())


def _add(index: dict, program_id: int, value) -> None:
    text = clean_region_text(value)
    if text:
        index.setdefault(program_id, set()).add(text)


def build_region_index(conn) -> dict:
    """프로그램별 지역 후보를 한 번에 구성한다.

    region_display와 지역 구조화 필드가 우선이며, e나라도움은 원본 JSON의
    시도·시군구·수행지역 필드도 보완적으로 읽는다. 원본은 읽기만 한다.
    """
    index = {}

    for row in conn.execute(
        "SELECT id, region_display FROM programs WHERE region_display IS NOT NULL"
    ).fetchall():
        _add(index, row["id"], row["region_display"])

    for row in conn.execute(
        """
        SELECT program_id, field_value
        FROM program_fields
        WHERE field_name = '지역' AND field_value IS NOT NULL
        """
    ).fetchall():
        _add(index, row["program_id"], row["field_value"])

    for row in conn.execute(
        """
        SELECT p.id, r.raw_json
        FROM programs p
        JOIN raw_api_responses r
          ON r.source = p.source AND r.source_item_id = p.source_item_id
        WHERE p.source = 'enara' AND r.raw_json IS NOT NULL
        """
    ).fetchall():
        try:
            payload = json.loads(row["raw_json"])
        except (TypeError, ValueError):
            continue

        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in _REGION_KEYS:
                        _add(index, row["id"], child)
                    else:
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)

    return index


def matches_region(values, requested: str) -> bool:
    """입력 지역에 맞거나 전국 대상인 경우만 통과시킨다."""
    requested = clean_region_text(requested).lower()
    if not requested:
        return True
    cleaned = [clean_region_text(value).lower() for value in values if value]
    if any(requested in value for value in cleaned):
        return True
    return any(marker.lower() in value for value in cleaned for marker in _NATIONWIDE_MARKERS)

