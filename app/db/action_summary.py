"""
목록/상세 화면에 "보조금 규모 / 신청대상 / 제외대상 / 창업업력 /
지원기간 / 지원방법" 요약을
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
EXCLUSION_MARKER_RE = re.compile(
    r"(?:지원\s*제외\s*대상|신청\s*제외\s*대상|제외\s*대상|제외\s*조건|지원\s*제외)"
)
STARTUP_AGE_PATTERNS = [
    re.compile(r"예비\s*창업자[^\n,;]*"),
    re.compile(r"창업\s*후\s*[^\n.;,]+"),
    re.compile(r"업력\s*[:：]?\s*[^\n.;,]+"),
    re.compile(r"설립\s*일[^\n.;,]+"),
]

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


def _text_values(raw: Optional[dict]) -> list[str]:
    """원본 딕셔너리의 문자열 값만 모아 검색용으로 반환한다."""
    if not raw:
        return []
    return [str(value) for value in raw.values() if isinstance(value, str) and value.strip()]


def _find_exclusion(texts: list[str]) -> Optional[str]:
    """명시적인 제외대상/제외조건 문구만 추출한다. 없으면 추측하지 않는다."""
    for text in texts:
        normalized = text.replace("\\r\\n", "\n").replace("\\n", "\n")
        lines = normalized.splitlines() or [normalized]
        for index, line in enumerate(lines):
            if not EXCLUSION_MARKER_RE.search(line):
                continue
            collected = [line.strip()]
            for following in lines[index + 1:]:
                stripped = following.strip()
                if not stripped:
                    break
                if re.match(r"^(?:[ㅇ○◦-]\s*)?[가-힣A-Za-z][^:：]{0,30}[:：]", stripped):
                    break
                collected.append(stripped)
            return " ".join(collected)
    return None


def _find_startup_age(texts: list[str]) -> Optional[str]:
    """창업업력·설립일 조건을 명시한 원문만 추출한다."""
    for text in texts:
        normalized = text.replace("\\r\\n", "\n").replace("\\n", "\n")
        for pattern in STARTUP_AGE_PATTERNS:
            match = pattern.search(normalized)
            if match:
                return match.group(0).strip()
    return None


def _kocca_summary(conn, source_item_id: str) -> dict:
    raw = _fetch_raw_item(conn, "kocca", source_item_id)
    if not raw or not raw.get("content"):
        return {"eligibility": CHECK_ORIGINAL, "excluded": CHECK_ORIGINAL,
                "startup_age": NO_INFO, "method": CHECK_ORIGINAL}
    sections = _parse_kocca_sections(raw["content"])
    eligibility = _find_by_keyword(sections, KOCCA_ELIGIBILITY_KEYWORDS)
    method = _find_by_keyword(sections, KOCCA_METHOD_KEYWORDS)
    texts = _text_values(raw)
    return {
        "eligibility": eligibility or CHECK_ORIGINAL,
        "excluded": _find_exclusion(texts) or CHECK_ORIGINAL,
        "startup_age": _find_startup_age(texts) or NO_INFO,
        "method": method or CHECK_ORIGINAL,
    }


def _bizinfo_summary(conn, source_item_id: str) -> dict:
    # response_type='item'으로 저장된 raw_api_responses는 항목 자체가 최상위
    # 딕셔너리다(jsonArray로 감싸여 있지 않음 — response_type='page' 저장본과
    # 다르다. 2026-09-07 확인).
    raw = _fetch_raw_item(conn, "bizinfo", source_item_id)
    if not raw:
        return {"excluded": CHECK_ORIGINAL, "startup_age": NO_INFO,
                "method": CHECK_ORIGINAL}
    method = raw.get("reqstMthPapersCn")
    texts = _text_values(raw)
    return {
        "excluded": _find_exclusion(texts) or CHECK_ORIGINAL,
        "startup_age": _find_startup_age(texts) or NO_INFO,
        "method": method.strip() if method else NO_INFO,
    }


def _public_benefits_summary(conn, source_item_id: str) -> dict:
    raw = _fetch_raw_item(conn, "public_benefits", source_item_id)
    if not raw:
        return {"excluded": CHECK_ORIGINAL, "startup_age": NO_INFO,
                "method": CHECK_ORIGINAL}
    method = raw.get("신청방법")
    texts = _text_values(raw)
    return {
        "excluded": _find_exclusion(texts) or CHECK_ORIGINAL,
        "startup_age": _find_startup_age(texts) or NO_INFO,
        "method": method.strip() if method else NO_INFO,
    }


def _strip_cdata(value):
    """e나라도움 원본은 XML 기반 API라, JSON으로 받아도 필드 값 안에
    '<![CDATA[...]]>' 래퍼가 문자열째로 그대로 남아있는 경우가 있다
    (2026-09-09 실제 저장된 원본에서 확인 — GOVSUBY, EXCL_TRGET_CN,
    REQST_RCEPT_MTH_CN 등). 어댑터의 to_standard_program()은 자체 _clean()
    으로 이미 벗기지만, 이 화면 요약은 raw_json을 별도로 직접 읽으므로
    여기서도 한 번 더 벗겨야 화면에 래퍼가 그대로 노출되지 않는다."""
    if not isinstance(value, str):
        return value
    return value.replace("<![CDATA[", "").replace("]]>", "").strip()


def _clean_enara_raw(raw: dict) -> dict:
    return {key: _strip_cdata(value) for key, value in raw.items()}


def _enara_summary(conn, source_item_id: str) -> dict:
    raw = _fetch_raw_item(conn, "enara", source_item_id)
    if not raw:
        return {"amount": NO_INFO, "excluded": CHECK_ORIGINAL, "startup_age": NO_INFO,
                "method": CHECK_ORIGINAL}
    raw = _clean_enara_raw(raw)
    amount = None
    for key in ("GOVSUBY", "SPORT_BGAMT", "TGYL_YEAR_BSNS_AMOUNT"):
        value = raw.get(key)
        if value not in (None, "", "0", 0):
            amount = str(value).strip()
            break
    if amount and re.fullmatch(r"\d+", amount):
        amount = f"{int(amount):,}원"
    texts = _text_values(raw)
    method = raw.get("REQST_RCEPT_MTH_CN")
    return {
        "amount": amount or NO_INFO,
        "excluded": _find_exclusion(texts) or raw.get("EXCL_TRGET_CN") or CHECK_ORIGINAL,
        "startup_age": _find_startup_age(texts) or NO_INFO,
        "method": method.strip() if method else NO_INFO,
    }


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
        return {"excluded": CHECK_ORIGINAL, "startup_age": CHECK_ORIGINAL,
                "method": CHECK_ORIGINAL}
    parts = []
    for field_key, label in KSTARTUP_METHOD_FIELDS:
        value = item.get(field_key)
        if value:
            parts.append(f"{label}: {value.strip()}")
    target_texts = [item.get("aply_trgt", ""), item.get("aply_trgt_ctnt", "")]
    content_texts = [item.get("pbanc_ctnt", "")]
    age = item.get("biz_enyy")
    if age:
        age = re.sub(r"(?<=\d)년미만", "년 미만", age)
        age = re.sub(r",\s*", ", ", age)
    return {
        "excluded": _find_exclusion(target_texts + content_texts) or CHECK_ORIGINAL,
        "startup_age": age or NO_INFO,
        "method": "; ".join(parts) if parts else NO_INFO,
    }


def build_action_summary(conn, program_row) -> dict:
    """
    program_row: programs 테이블의 한 행(dict 또는 sqlite3.Row, 최소한
    source/source_item_id/application_period_display/target_company_display/
    amount_display 컬럼을 포함해야 함).

    반환: {"amount": str, "eligibility": str, "excluded": str,
    "startup_age": str, "period": str, "method": str}
    모든 키는 항상 사람이 읽을 문자열이다(빈 값이어도 NO_INFO/CHECK_ORIGINAL로
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
    elif source == "enara":
        extra = _enara_summary(conn, source_item_id)

    if "amount" in extra and _is_missing_display(program_row["amount_display"]):
        amount = extra["amount"]

    if "eligibility" in extra and _is_missing_display(program_row["target_company_display"]):
        eligibility = extra["eligibility"]
    if "method" in extra:
        method = extra["method"]

    excluded = extra.get("excluded", CHECK_ORIGINAL)
    startup_age = extra.get("startup_age", NO_INFO)

    return {
        "amount": amount,
        "eligibility": eligibility,
        "excluded": excluded,
        "startup_age": startup_age,
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


def _is_missing_display(value: Optional[str]) -> bool:
    """적재 과정에서 들어온 placeholder를 실제 대상 정보 없음으로 취급한다."""
    return not value or value.strip() in {"-", "정보 없음", "미추출"}
