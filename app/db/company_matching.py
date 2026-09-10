"""
AI/외부 API 없이 회사 프로필과 지원사업 공고를 비교하는 규칙 기반 매칭 엔진.

원칙 (전부 사용자 요청에 따른 것):
  - 외부 AI API나 토큰을 전혀 쓰지 않는다 — 이 파일 전체가 텍스트 키워드
    비교/날짜 계산 같은 순수 규칙으로만 이루어진다.
  - 공고 원문에 없는 정보는 절대 "탈락(불일치)"로 처리하지 않는다 —
    항상 "확인 필요"로 남긴다. "불일치"는 아래처럼 원문에 명시적인 반대
    근거가 있을 때만 매긴다: 지역이 명시적으로 다름, 접수기간이 이미
    마감됨, 제외대상 문구에 회사 조건이 명시적으로 해당함, 업력 상한을
    명시적으로 초과함.
  - 출처(source)별로 다른 코드를 두지 않는다 — programs/program_fields/
    action_summary.build_action_summary()처럼 이미 모든 출처가 공유하는
    공통 구조만 사용한다. 그래야 나중에 새 출처(NTIS 등)가 추가돼도
    이 파일을 고치지 않고 그대로 적용된다.
  - programs/program_fields 등 기존 공고 표는 읽기만 하고 전혀 쓰지 않는다.

세 가지 결과 분류: "적합 가능성 높음" / "검토 필요" / "조건 불일치".
"""

import html
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_summary import build_action_summary, NO_INFO, CHECK_ORIGINAL  # noqa: E402

# 대한민국 17개 광역시·도 — 제목 맨 앞 "[지역]" 표기가 진짜 지역인지
# 판별하는 데 쓴다("[수정/상시공고]"처럼 지역이 아닌 대괄호 표기와
# 구분하기 위해 고정된 실제 지역명 목록으로만 판단한다).
KNOWN_REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

_REGION_TAG_RE = re.compile(r"^\[(.+?)\]")
_AGE_LIMIT_RE = re.compile(r"(?:창업|업력|설립)\s*(?:후)?\s*[:：]?\s*(\d+)\s*년\s*(?:이내|미만|이하)")

VERDICT_GOOD = "적합 가능성 높음"
VERDICT_REVIEW = "검토 필요"
VERDICT_MISMATCH = "조건 불일치"

DIMENSION_LABELS = {
    "region": "지역",
    "industry": "업종·지원분야",
    "business_age": "업력",
    "target": "신청대상",
    "excluded": "제외대상",
    "period": "지원기간",
    "amount": "지원금액",
    "employee_count": "직원 수",
    "revenue": "매출 규모",
}


# 같은 분야를 공고마다 다르게 쓰는 대표적인 표현만 비교용으로 확장한다.
TERM_ALIASES = {
    "제조업": {"제조업", "제조", "제조기업", "중소제조", "중소제조업체"},
    "소상공인": {"소상공인", "소상공", "소기업"},
    "중소기업": {"중소기업", "중소기업체", "중소제조기업"},
    "수출": {"수출", "해외진출", "해외시장", "무역", "수출기업"},
    "연구개발": {"연구개발", "r&d", "기술개발", "기술혁신"},
    "디지털 전환": {"디지털전환", "디지털화", "스마트공장", "스마트제조"},
    "정책자금": {"정책자금", "정책금융", "융자", "대출", "자금"},
    "판로": {"판로", "마케팅", "시장개척", "판매촉진"},
}


def _plain_text(value: object) -> str:
    """HTML과 불필요한 개행을 제거한 비교용 문자열."""
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]*>", " ", text)
    return " ".join(text.replace("\\n", " ").split())


def _compact(value: object) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣+#]", "", _plain_text(value).lower())


def _term_variants(term: str) -> set[str]:
    cleaned = _plain_text(term).strip()
    compact = _compact(cleaned)
    variants = {cleaned.lower(), compact}
    for canonical, aliases in TERM_ALIASES.items():
        alias_compact = {_compact(alias) for alias in aliases}
        if compact == _compact(canonical) or compact in alias_compact:
            variants.update(alias.lower() for alias in aliases)
            variants.update(alias_compact)
    return {value for value in variants if value}


def _contains_term(text: str, term: str) -> bool:
    normalized = _compact(text)
    return any(_compact(variant) in normalized for variant in _term_variants(term))


def _program_field_text(conn, program_id: int) -> str:
    """프로그램에 저장된 구조화 필드와 원문 섹션을 비교 대상으로 합친다."""
    rows = conn.execute(
        "SELECT field_name, field_value, section_text FROM program_fields WHERE program_id = ?",
        (program_id,),
    ).fetchall()
    parts = []
    for row in rows:
        parts.extend((row["field_name"], row["field_value"], row["section_text"]))
    return " ".join(_plain_text(part) for part in parts if part)


def _extract_limit(text: str, patterns: list[str]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, _plain_text(text), flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def extract_region_tag(title: str) -> Optional[str]:
    match = _REGION_TAG_RE.match(title or "")
    if not match:
        return None
    tag = match.group(1).strip()
    return tag if tag in KNOWN_REGIONS else None


def _compare_region(company: dict, region_tag: Optional[str]):
    if not region_tag:
        return ("확인 필요", "공고 제목에 지역 표시가 없습니다(전국 대상일 수 있음)")
    company_region = (company.get("region") or "").strip()
    if not company_region:
        return ("확인 필요", "회사 소재지 정보가 입력되지 않았습니다")
    if company_region == region_tag or region_tag in company_region or company_region in region_tag:
        return ("일치", f"공고 지역({region_tag})이 회사 소재지({company_region})와 일치")
    return ("불일치", f"공고는 {region_tag} 지역 한정 공고이나 회사 소재지는 {company_region}")


def _compare_industry(company: dict, text_pool: str):
    terms = []
    if company.get("industry"):
        terms.append(company["industry"].strip())
    if company.get("desired_fields"):
        terms.extend(t.strip() for t in company["desired_fields"].split(",") if t.strip())
    terms = [t for t in terms if t]
    if not terms:
        return ("확인 필요", "회사의 업종/희망 지원분야 정보가 입력되지 않았습니다")
    hits = [t for t in terms if _contains_term(text_pool, t)]
    if hits:
        return ("일치", "업종·지원분야 일치: " + ", ".join(hits))
    return ("확인 필요", "공고의 지원분야·사업요약에서 회사의 업종/희망 지원분야와 일치하는 항목을 찾지 못함")


def _company_age_years(company: dict) -> Optional[float]:
    founded = company.get("founded_date")
    if founded:
        try:
            y, m, d = (int(part) for part in founded.split("-"))
            return (date.today() - date(y, m, d)).days / 365.25
        except (ValueError, TypeError):
            pass
    age = company.get("business_age_years")
    return float(age) if age is not None else None


def _compare_business_age(company: dict, combined_text: str):
    match = _AGE_LIMIT_RE.search(combined_text or "")
    if not match:
        return ("확인 필요", "공고에 업력(창업 연차) 제한이 명시되어 있지 않습니다")
    limit_years = int(match.group(1))
    age = _company_age_years(company)
    if age is None:
        return ("확인 필요", f"공고는 창업 {limit_years}년 이내 조건으로 보이나 회사 업력 정보가 없습니다")
    if age <= limit_years:
        return ("일치", f"회사 업력 약 {age:.1f}년 — 공고 기준(창업 {limit_years}년 이내) 충족")
    return ("불일치", f"회사 업력 약 {age:.1f}년 — 공고 기준(창업 {limit_years}년 이내) 초과")


def _compare_target(company: dict, eligibility_text: str):
    if not eligibility_text or eligibility_text in (NO_INFO, CHECK_ORIGINAL):
        return ("확인 필요", "공고에 신청대상 정보가 없습니다")
    hits = []
    if company.get("company_type") == "소상공인" and _contains_term(eligibility_text, "소상공인"):
        hits.append("소상공인")
    if company.get("company_type") in ("중소기업", "중견기업") and _contains_term(eligibility_text, "중소기업"):
        hits.append(company["company_type"])
    if company.get("exports") == "예" and _contains_term(eligibility_text, "수출"):
        hits.append("수출기업")
    if company.get("rnd") == "예" and _contains_term(eligibility_text, "연구개발"):
        hits.append("연구개발기업")
    if company.get("industry") and _contains_term(eligibility_text, company["industry"]):
        hits.append(f"업종({company['industry']})")
    if hits:
        return ("일치", "신청대상 조건에 해당: " + ", ".join(hits))
    return ("확인 필요", "신청대상 문구에서 회사 조건과 뚜렷하게 일치하는 부분을 찾지 못함 — 원문 확인 권장")


def _compare_excluded(company: dict, excluded_text: str):
    if not excluded_text or excluded_text in (NO_INFO, CHECK_ORIGINAL):
        return ("해당없음", "제외대상이 명시되어 있지 않습니다")
    hits = []
    candidates = []
    if company.get("company_type"):
        candidates.append(company["company_type"])
    if company.get("exports") == "예":
        candidates.append("수출")
    if company.get("rnd") == "예":
        candidates.append("연구개발")
    if company.get("industry"):
        candidates.append(company["industry"])
    if any(_contains_term(excluded_text, term) and "제외" in excluded_text for term in candidates):
        hits.append("제외대상 문구에 회사 조건과 관련된 제외 표현이 포함되어 있어 확인이 필요합니다")
    if hits:
        return ("불일치", " / ".join(hits))
    return ("확인 필요", "제외대상 문구가 있습니다 — 회사 조건과 겹치는지 원문에서 직접 확인해 주세요")


def _compare_period(status_computed: Optional[str]):
    if status_computed in ("접수중", "예정", "마감임박"):
        return ("일치", f"현재 접수 상태: {status_computed}")
    if status_computed == "마감":
        return ("불일치", "이미 접수가 마감된 공고입니다")
    return ("확인 필요", f"접수 상태를 원문에서 확인해 주세요({status_computed or '정보없음'})")


def _describe_amount(amount_text: Optional[str]):
    if not amount_text or amount_text == NO_INFO:
        return ("확인 필요", "공고에 지원금액 정보가 없습니다")
    return ("참고", f"공고 지원금액: {amount_text}")


def _compare_employee_count(company: dict, text_pool: str):
    employee_count = company.get("employee_count")
    if employee_count in (None, ""):
        return ("참고", "회사 직원 수가 입력되지 않아 직원 수 조건은 비교하지 않음")
    limit = _extract_limit(text_pool, [
        r"(?:근로자|직원|종업원|상시근로자)\s*([\d,]+)\s*명\s*(?:미만|이하|미만인)",
        r"([\d,]+)\s*명\s*(?:미만|이하)의\s*(?:기업|업체|사업자)",
    ])
    if limit is None:
        return ("참고", "공고에 직원 수 기준이 없어 매칭에 사용하지 않음")
    if float(employee_count) <= limit:
        return ("일치", f"회사 직원 수 {employee_count}명 — 공고 기준 {int(limit)}명 이하")
    return ("불일치", f"회사 직원 수 {employee_count}명 — 공고 기준 {int(limit)}명 초과")


def _compare_revenue(company: dict, text_pool: str):
    revenue = _plain_text(company.get("revenue_range"))
    if not revenue:
        return ("참고", "회사 매출 규모가 입력되지 않아 매출 조건은 비교하지 않음")
    limit = _extract_limit(text_pool, [
        r"매출(?:액)?[^\d]{0,15}([\d,]+)\s*(?:억|만원|원)\s*(?:이하|미만)",
    ])
    if limit is None:
        return ("참고", "공고에 매출 기준이 없어 매칭에 사용하지 않음")
    if "억" in revenue:
        numbers = re.findall(r"[\d,]+(?:\.\d+)?", revenue)
        if numbers and float(numbers[-1].replace(",", "")) <= limit:
            return ("일치", f"입력한 매출 구간({revenue})이 공고 기준 이내일 가능성이 높음")
    return ("확인 필요", f"공고 매출 상한과 입력 구간({revenue})의 정확한 비교가 필요합니다")


def compute_overall_verdict(dimensions: dict):
    """
    dimensions: {키: (판정, 설명)} — 판정은 '일치'/'불일치'/'확인 필요'/'해당없음'/'참고'.

    규칙 (전부 사용자가 지정한 3단계 분류를 만들기 위한 것 — AI 판단 아님):
      1) 하나라도 '불일치'가 있으면 -> 조건 불일치.
      2) '일치'가 2개 이상이고 지원기간이 '일치'이면 -> 적합 가능성 높음.
      3) 그 외 -> 검토 필요.
    """
    mismatched = [k for k, v in dimensions.items() if v[0] == "불일치"]
    if mismatched:
        return VERDICT_MISMATCH, mismatched

    matched = [k for k, v in dimensions.items() if v[0] == "일치"]
    needs_review = [k for k, v in dimensions.items() if v[0] == "확인 필요"]
    period_ok = dimensions.get("period", ("",))[0] == "일치"

    if len(matched) >= 2 and period_ok:
        return VERDICT_GOOD, needs_review
    return VERDICT_REVIEW, needs_review


def match_company_to_program(conn, company: dict, program_row: dict,
                             program_field_text: Optional[str] = None) -> dict:
    """program_row는 최소 id/title/source/source_item_id/status_computed +
    action_summary가 요구하는 컬럼(application_period_display 등)을 포함해야 함."""
    summary = build_action_summary(conn, program_row)

    class_rows = conn.execute(
        """
        SELECT cn.display_name FROM program_classifications pc
        JOIN classification_nodes cn ON cn.id = pc.node_id
        WHERE pc.program_id = ?
        """,
        (program_row["id"],),
    ).fetchall()
    classification_text = " ".join(r["display_name"] for r in class_rows if r["display_name"])
    field_text = (
        program_field_text
        if program_field_text is not None
        else _program_field_text(conn, program_row["id"])
    )
    summary_text = " ".join(
        str(summary.get(key, ""))
        for key in ("eligibility", "excluded", "startup_age", "method")
    )
    text_pool = f"{program_row.get('title', '')} {classification_text} {field_text} {summary_text}"

    region_tag = extract_region_tag(program_row.get("title"))
    combined_text_for_age = f"{text_pool} {summary['eligibility']} {summary['startup_age']}"

    dimensions = {
        "region": _compare_region(company, region_tag),
        "industry": _compare_industry(company, text_pool),
        "business_age": _compare_business_age(company, combined_text_for_age),
        # 기업마당의 대상기업 필드와 사업요약에도 신청대상이 반복해서
        # 들어오므로, 화면 요약만이 아니라 저장된 구조화 원문까지 함께 본다.
        "target": _compare_target(company, f"{summary['eligibility']} {field_text}"),
        "excluded": _compare_excluded(company, summary["excluded"]),
        "period": _compare_period(program_row.get("status_computed")),
        "amount": _describe_amount(summary["amount"]),
        "employee_count": _compare_employee_count(company, text_pool),
        "revenue": _compare_revenue(company, text_pool),
    }
    verdict, needs_review = compute_overall_verdict(dimensions)

    matched_count = sum(1 for state, _ in dimensions.values() if state == "일치")
    review_count = sum(1 for state, _ in dimensions.values() if state == "확인 필요")
    mismatch_count = sum(1 for state, _ in dimensions.values() if state == "불일치")

    return {
        "program_id": program_row["id"],
        "title": program_row.get("title"),
        "source": program_row.get("source"),
        "verdict": verdict,
        "dimensions": dimensions,
        "needs_review": needs_review,
        # 화면 정렬용 점수. AI나 외부 API가 아니라 조건 판정 개수다.
        "matched_count": matched_count,
        "review_count": review_count,
        "mismatch_count": mismatch_count,
    }


def match_company_to_all_programs(conn, company: dict) -> list:
    rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT id, title, source, source_item_id, status_computed,
                   application_period_display, amount_display,
                   target_company_display, region_display
            FROM programs
            """
        ).fetchall()
    ]
    field_text_by_program = {}
    for field_row in conn.execute(
        "SELECT program_id, field_name, field_value, section_text FROM program_fields"
    ).fetchall():
        field_text_by_program.setdefault(field_row["program_id"], []).extend(
            [field_row["field_name"], field_row["field_value"], field_row["section_text"]]
        )
    field_text_by_program = {
        program_id: " ".join(_plain_text(value) for value in values if value)
        for program_id, values in field_text_by_program.items()
    }
    results = [
        match_company_to_program(
            conn, company, row, field_text_by_program.get(row["id"], "")
        )
        for row in rows
    ]
    order = {VERDICT_GOOD: 0, VERDICT_REVIEW: 1, VERDICT_MISMATCH: 2}
    # 먼저 판정 그룹을 나누고, 같은 그룹에서는 회사 조건과 실제로
    # 일치한 항목이 많은 공고를 우선한다. 확인 필요 항목이 적은 공고가
    # 그 다음이며, 마감일은 최종 동점일 때만 서버 화면에서 보조한다.
    results.sort(key=lambda r: (
        order[r["verdict"]],
        -r["matched_count"],
        r["review_count"],
        r["mismatch_count"],
        r["program_id"],
    ))
    return results
