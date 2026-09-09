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
}


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
    hits = [t for t in terms if t in text_pool]
    if hits:
        return ("일치", "업종·지원분야 일치: " + ", ".join(hits))
    return ("확인 필요", "공고 제목·분류에서 회사의 업종/희망 지원분야와 일치하는 항목을 찾지 못함")


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
    if company.get("company_type") == "소상공인" and "소상공인" in eligibility_text:
        hits.append("소상공인")
    if company.get("company_type") in ("중소기업", "중견기업") and "중소기업" in eligibility_text:
        hits.append("중소기업")
    if company.get("exports") == "예" and "수출" in eligibility_text:
        hits.append("수출기업")
    if company.get("rnd") == "예" and ("연구개발" in eligibility_text or "R&D" in eligibility_text.upper()):
        hits.append("연구개발기업")
    if company.get("industry") and company["industry"] in eligibility_text:
        hits.append(f"업종({company['industry']})")
    if hits:
        return ("일치", "신청대상 조건에 해당: " + ", ".join(hits))
    return ("확인 필요", "신청대상 문구에서 회사 조건과 뚜렷하게 일치하는 부분을 찾지 못함 — 원문 확인 권장")


def _compare_excluded(company: dict, excluded_text: str):
    if not excluded_text or excluded_text in (NO_INFO, CHECK_ORIGINAL):
        return ("해당없음", "제외대상이 명시되어 있지 않습니다")
    hits = []
    if company.get("company_type") == "소상공인" and "소상공인" in excluded_text and "제외" in excluded_text:
        hits.append("제외대상 문구에 '소상공인 제외' 표현이 포함되어 있어 확인이 필요합니다")
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


def match_company_to_program(conn, company: dict, program_row: dict) -> dict:
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
    text_pool = f"{program_row.get('title', '')} {classification_text}"

    region_tag = extract_region_tag(program_row.get("title"))
    combined_text_for_age = f"{summary['eligibility']} {summary['startup_age']}"

    dimensions = {
        "region": _compare_region(company, region_tag),
        "industry": _compare_industry(company, text_pool),
        "business_age": _compare_business_age(company, combined_text_for_age),
        "target": _compare_target(company, summary["eligibility"]),
        "excluded": _compare_excluded(company, summary["excluded"]),
        "period": _compare_period(program_row.get("status_computed")),
        "amount": _describe_amount(summary["amount"]),
    }
    verdict, needs_review = compute_overall_verdict(dimensions)

    return {
        "program_id": program_row["id"],
        "title": program_row.get("title"),
        "source": program_row.get("source"),
        "verdict": verdict,
        "dimensions": dimensions,
        "needs_review": needs_review,
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
    results = [match_company_to_program(conn, company, row) for row in rows]
    order = {VERDICT_GOOD: 0, VERDICT_REVIEW: 1, VERDICT_MISMATCH: 2}
    results.sort(key=lambda r: (order[r["verdict"]], r["program_id"]))
    return results
