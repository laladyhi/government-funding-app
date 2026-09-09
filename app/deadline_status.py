"""공고 접수기간을 이용한 화면 표시용 상태 계산."""

import re
from datetime import date, datetime
from typing import Optional, Tuple


_DATE_RE = re.compile(r"(\d{4})[-./]?(\d{2})[-./]?(\d{2})")


def _parse_date(value: str) -> Optional[date]:
    match = _DATE_RE.search(value or "")
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def parse_period(period_raw: str) -> Tuple[Optional[date], Optional[date]]:
    """YYYYMMDD 또는 YYYY-MM-DD 기간에서 시작일·종료일을 추출한다."""
    values = _DATE_RE.findall(period_raw or "")
    dates = []
    for year, month, day in values[:2]:
        try:
            dates.append(date(int(year), int(month), int(day)))
        except ValueError:
            pass
    if len(dates) == 2:
        return dates[0], dates[1]
    return None, None


def get_deadline_status(period_raw: str, today: Optional[date] = None) -> dict:
    """목록 정렬과 색상 배지에 사용할 상태를 반환한다."""
    today = today or date.today()
    start, end = parse_period(period_raw or "")
    missing = {
        "label": "기간 확인 필요",
        "class_name": "deadline-unknown",
        "rank": 4,
        "days_left": None,
        "end_date": None,
    }
    if not start or not end:
        return missing
    days_left = (end - today).days
    if today < start:
        return {"label": "접수예정", "class_name": "deadline-upcoming", "rank": 2,
                "days_left": days_left, "end_date": end}
    if today > end:
        return {"label": "마감", "class_name": "deadline-closed", "rank": 3,
                "days_left": days_left, "end_date": end}
    if days_left <= 7:
        return {"label": "마감임박", "class_name": "deadline-urgent", "rank": 0,
                "days_left": days_left, "end_date": end}
    return {"label": "접수중", "class_name": "deadline-open", "rank": 1,
            "days_left": days_left, "end_date": end}


def deadline_sort_key(program: dict) -> tuple:
    state = program["deadline_state"]
    end_date = state.get("end_date")
    if state["rank"] in (0, 1, 2) and end_date:
        return (state["rank"], end_date, -int(program["id"]))
    return (state["rank"], date.max, -int(program["id"]))
