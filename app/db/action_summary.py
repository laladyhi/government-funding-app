"""
목록/상세 화면에 "보조금 규모 / 지원자격 / 지원기간 / 지원방법" 4줄 요약을
보여주기 위한 헬퍼.

원칙:
  - 운영 DB 스키마나 데이터를 전혀 바꾸지 않는다. programs 테이블에 이미
    있는 값(application_period_display, target_company_display,
    amount_display)과, 이미 저장되어 있는 raw_api_responses.raw_json
    (원본 그대로)만 읽는다. 새 API 호출은 하지 않는다.
  - "지원방법"은 어느 출처든 program_fields에 별도로 저장된 적이 없어서
    (기업마당 로더도, 표준 로더도 이 필드를 뽑아 저장하지 않았다), 화면에
    보여줄 때 원본에서 즉석으로 읽어온다 — DB에는 아무것도 쓰지 않는다.
  - K-Startup(kstartup)은 raw_api_responses에 원본이 없다(2026-09-04
    최초 적재 당시 이 표에 기록하는 코드가 아직 없었던 시기의 데이터 —
    docs/raw-data-hash-policy.md, test_hash_consistency.py 참고). 대신
    당시 적재에 실제로 쓰인 원본 fixture(collector/fixtures/
    kstartup_real_sample_20260904.json, _is_real_data: true로 확인된
    실제 캡처 데이터)를 그대로 읽어 pbanc_sn으로 매칭한다. 이 파일도
    이미 로컬에 있는 것을 읽을 뿐, 새로 API를 부르지 않는다.
  - 실제 원문에 없는 값은 "정보 없음"으로, 원문에 있을 법하지만 이 코드가
    안전하게 뽑아내지 못한 경우(예: KOCCA의 자유서식 content 파싱 실패)는
    "공식 원문 확인 필요"로 표시한다 — 절대 추측해서 채우지 않는다.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KSTARTUP_FIXTURE_PATH = PROJECT_ROOT / "collector" / "fixtures" / "kstartup_real_sample_20260904.json"

NO_INFO = "정보 없음"
CHECK_ORIGINAL = "공식 원문 확인 필요"

# KOCCA content 필드 안의 자유서식 "섹션명:내용" 중, 어떤 헤더가 지원자격/
# 지원방법에 해당하는지 판단하기 위한 키워드. 공고마다 헤더 문구가
# 조금씩 달라서("지원대상 및 참가자격" / "지원대상 및 신청자격" 등)
# 완전일치 대신 포함 여부로 찾는다 — 그래도 못 찾으면 지어내지 않고
# CHECK_ORIGINAL로 정직하게 표시한다.
KOCCA_ELIGIBILITY_KEYWORDS = ["지원대상", "참가자격", "신청자격", "모집대상"]
KOCCA_METHOD_KEYWORDS = ["신청방법"]

# K-Startup 원본의 접수채널별 필드 -> 화면에 보여줄 라벨.
KSTARTUP_METHOD_FIELDS = [
    ("aply_mthd_onli_rcpt_istc", "온라인 접수"),
    ("aply_mthd_eml_rcpt_istc", "이메일 접수"),
    ("aply_mthd_fax_rcpt_istc", "팩스 접수"),
    ("aply_mthd_pssr_rcpt_istc", "우편 접수"),
    ("aply_mthd_vst_rcpt_istc", "방문 접수"),
    ("aply_mthd_etc_istc", "기타 접수"),
]

_kstartup_fixture_cache: Optional[dict] = None


def _load_kstartup_fixture() -> dict:
    """pbanc_sn -> raw item 딕셔너리. 파일이 없으면 빈 딕셔너리(정직하게 실패)."""
    global _kstartup_fixture_cache
    if _kstartup_fixture_cache is not None:
        return _kstartup_fixture_cache
    _kstartup_fixture_cache = {}
    if not KSTARTUP_FIXTURE_PATH.exists():
        return _kstartup_fixture_cache
    try:
        data = json.loads(KSTARTUP_FIXTURE_PATH.read_bytes().decode("utf-8"))
    except (ValueError, OSError):
        return _kstartup_fixture_cache
    if not data.get("_is_real_data"):
        # 실제 데이터로 확인된 파일이 아니면(가상 fixture로 바뀌었다면)
        # 절대 화면에 쓰지 않는다 — 안전장치.
        return _kstartup_fixture_cache
    for item in data.get("items", []):
        pbanc_sn = item.get("pbanc_sn")
        if pbanc_sn:
            _kstartup_fixture_cache[str(pbanc_sn)] = item
    return _kstartup_fixture_cache


def _fetch_raw_item(conn, source: str, source_item_id: str) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT raw_json FROM raw_api_responses
        WHERE source = ? AND source_item_id = ? AND response_type = 'item'
        ORDER BY collected_at DESC LIMIT 1
        """,
        (source, source_item_id),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["raw_json"])
    except ValueError:
        return None


def _parse_kocca_sections(content: str) -> dict:
    """
    KOCCA content는 "섹션명:내용" 블록을 리터럴 백슬래시-n("\\n" 두 글자)으로
    이어붙인 자유서식이다(2026-09-07 실제 응답으로 확인). 완전히 표준화된
    구조가 아니므로 헤더 텍스트를 그대로 키로 하는 딕셔너리만 만들고,
    호출부에서 키워드로 찾는다.
    """
    sections = {}
    for part in content.split("\\n"):
        if ":" not in part:
            continue
        head, _, body = part.partition(":")
        head = head.strip()
        body = body.strip()
        if head and body:
            sections[head] = body
    return sections


def _find_by_keyword(sections: dict, keywords: list) -> Optional[str]:
    for head, body in sections.items():
        if any(kw in head for kw in keywords):
            return body
    return None


def _kocca_summary(conn, source_item_id: str) -> dict:
    raw = _fetch_raw_item(conn, "kocca", source_item_id)
    if not raw or not raw.get("content"):
        return {"eligibility": CHECK_ORIGINAL, "method": CHECK_ORIGINAL}
    sections = _parse_kocca_sections(raw["content"])
    eligibility = _find_by_keyword(sections, KOCCA_ELIGIBILITY_KEYWORDS)
    method = _find_by_keyword(sections, KOCCA_METHOD_KEYWORDS)
    return {
        "eligibility": eligibility or CHECK_ORIGINAL,
        "method": method or CHECK_ORIGINAL,
    }


def _bizinfo_summary(conn, source_item_id: str) -> dict:
    # response_type='item'으로 저장된 raw_api_responses는 항목 자체가 최상위
    # 딕셔너리다(jsonArray로 감싸여 있지 않음 — response_type='page' 저장본과
    # 다르다. 2026-09-07 확인).
    raw = _fetch_raw_item(conn, "bizinfo", source_item_id)
    if not raw:
        return {"method": CHECK_ORIGINAL}
    method = raw.get("reqstMthPapersCn")
    return {"method": method.strip() if method else NO_INFO}


def _public_benefits_summary(conn, source_item_id: str) -> dict:
    raw = _fetch_raw_item(conn, "public_benefits", source_item_id)
    if not raw:
        return {"method": CHECK_ORIGINAL}
    method = raw.get("신청방법")
    return {"method": method.strip() if method else NO_INFO}


_YYYYMMDD_PERIOD_RE = re.compile(r"^(\d{8})\s*~\s*(\d{8})$")


def _format_period(period_raw: str) -> str:
    """
    K-Startup/KOCCA는 신청기간을 'YYYYMMDD ~ YYYYMMDD' 원문 그대로 저장한다
    (구분자 없는 8자리 숫자). 값 자체는 바꾸지 않고 읽기 좋은 형식으로만
    다시 쓴다(DB에는 쓰지 않음, 화면 표시용) — 'YYYY-MM-DD ~ YYYY-MM-DD'
    형식(다른 출처와 동일)이 아닌 경우에는 원문을 그대로 둔다.
    """
    match = _YYYYMMDD_PERIOD_RE.match(period_raw.strip())
    if not match:
        return period_raw
    start, end = match.groups()
    fmt = lambda d: f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    return f"{fmt(start)} ~ {fmt(end)}"


def _kstartup_summary(source_item_id: str) -> dict:
    fixture = _load_kstartup_fixture()
    item = fixture.get(str(source_item_id))
    if not item:
        return {"method": CHECK_ORIGINAL}
    parts = []
    for field_key, label in KSTARTUP_METHOD_FIELDS:
        value = item.get(field_key)
        if value:
            parts.append(f"{label}: {value.strip()}")
    return {"method": "; ".join(parts) if parts else NO_INFO}


def build_action_summary(conn, program_row) -> dict:
    """
    program_row: programs 테이블의 한 행(dict 또는 sqlite3.Row, 최소한
    source/source_item_id/application_period_display/target_company_display/
    amount_display 컬럼을 포함해야 함).

    반환: {"amount": str, "eligibility": str, "period": str, "method": str}
    4개 키 모두 항상 사람이 읽을 문자열이다(빈 값이어도 NO_INFO/CHECK_ORIGINAL로
    채워짐 — 절대 None을 반환하지 않는다).
    """
    source = program_row["source"]
    source_item_id = program_row["source_item_id"]

    amount = program_row["amount_display"] or NO_INFO
    eligibility = program_row["target_company_display"] or NO_INFO
    period_raw = program_row["application_period_display"]
    period = _format_period(period_raw) if period_raw else NO_INFO
    method = NO_INFO

    extra = {}
    if source == "kocca":
        extra = _kocca_summary(conn, source_item_id)
    elif source == "bizinfo":
        extra = _bizinfo_summary(conn, source_item_id)
    elif source == "public_benefits":
        extra = _public_benefits_summary(conn, source_item_id)
    elif source == "kstartup":
        extra = _kstartup_summary(source_item_id)

    if "eligibility" in extra and (not program_row["target_company_display"]):
        eligibility = extra["eligibility"]
    if "method" in extra:
        method = extra["method"]

    return {
        "amount": amount,
        "eligibility": eligibility,
        "period": period,
        "method": method,
    }


def truncate_ko(text: str, length: int = 60) -> str:
    """목록 카드용 1~2줄 요약 — 원문을 자르기만 하고 내용은 바꾸지 않는다."""
    if not text:
        return text
    text = " ".join(text.split())  # 개행/중복 공백만 정리(내용 변경 아님)
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"
