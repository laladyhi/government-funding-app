"""
여러 기관 어댑터가 공유하는 신청기간 파싱 로직.

원래 collector/fetch_and_store.py 안에 있던 parse_application_period를
그대로(동작 변경 없이) 이 파일로 옮겼다 — 기업마당 전용 코드가 아니라
어떤 기관의 데이터든 재사용할 수 있는 공통 로직이기 때문이다.

원칙(항상 지킬 것): 날짜 형식이 아닌 원문("수시 접수", "예산 소진시까지" 등)
을 억지로 날짜로 해석하지 않는다. 해석이 안 되면 start/end는 None으로
두고, 원문은 호출한 쪽에서 별도로 그대로 보존한다.
"""

import re
from datetime import date, datetime


def parse_application_period(raw_text: str, today: date):
    """
    'YYYY-MM-DD ~ YYYY-MM-DD' 형태만 날짜로 해석한다. 그 외
    ('수시 접수', '예산 소진시까지', '회차별 상이' 등)는 원문 그대로 두고
    구조화하지 않는다.
    """
    if not raw_text:
        return {"start": None, "end": None, "status": "정보없음", "is_structured": False}

    match = re.match(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", raw_text.strip())
    if not match:
        return {"start": None, "end": None, "status": "비정형(원문 참조)", "is_structured": False}

    start = datetime.strptime(match.group(1), "%Y-%m-%d").date()
    end = datetime.strptime(match.group(2), "%Y-%m-%d").date()

    if today < start:
        status = "예정"
    elif today > end:
        status = "마감"
    elif (end - today).days <= 3:
        status = "마감임박"
    else:
        status = "접수중"

    return {"start": str(start), "end": str(end), "status": status, "is_structured": True}


def parse_yyyymmdd(value):
    """
    'YYYYMMDD'(8자리 숫자, 구분자 없음) 형식만 'YYYY-MM-DD'로 변환한다.
    K-Startup 실제 API 응답(pbanc_rcpt_bgng_dt 등)이 이 형식이다 —
    기업마당의 'YYYY-MM-DD ~ YYYY-MM-DD' 결합 형식과는 다르므로 별도
    함수로 둔다.

    형식이 아니거나(길이가 다름 등) 날짜로서 유효하지 않으면(예:
    존재하지 않는 13월) 억지로 해석하지 않고 None을 반환한다 — 호출한
    쪽에서 원문을 그대로 보존해야 한다.
    """
    if not value:
        return None
    value = value.strip()
    if not re.fullmatch(r"\d{8}", value):
        return None
    try:
        return str(datetime.strptime(value, "%Y%m%d").date())
    except ValueError:
        return None
