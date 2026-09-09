"""웹 화면(server.py)에서 쓰는 읽기 전용 DB 접근 헬퍼."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate import DB_PATH  # noqa: E402


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# 상세 화면에 표시할 9개 핵심 항목 + 라벨.
# DB에 값이 없으면 "미추출"로 정직하게 표시한다(추정해서 채우지 않는다).
DETAIL_FIELD_ORDER = [
    ("지원 대상", "대상기업"),
    ("신청 자격", "__missing__:신청 자격 정보는 API에 없습니다. 공고 원문에서 직접 확인이 필요합니다."),
    ("지원 금액", "지원금액"),
    ("신청 기간", "신청기간_원문"),
    ("지원 기간", "__missing__:지원 기간 정보는 API에 없습니다. 공고 원문/첨부파일 확인이 필요합니다."),
    ("지원 내용", "사업요약_HTML"),
    ("사용 가능한 비용", "__missing__:비용 사용 항목은 API에 없습니다. 첨부파일(공고문)에서 확인이 필요합니다."),
    ("평가 방법", "__missing__:평가 방법은 API에 없습니다. 공고 원문에서 확인이 필요합니다."),
    ("제출 서류", "__missing__:제출 서류 목록은 API에 없습니다. 신청 방법/첨부파일에서 확인이 필요합니다."),
]

# 참고용 부가 정보(핵심 9개 항목 외에 실제로 확보된 값들)
# "신청 방법"은 여기 있었지만 program_fields에 이 이름으로 저장하는
# 로더가 하나도 없어(기업마당 로더도, 표준 로더도) 모든 공고에서 항상
# "(값 없음)"만 나왔다 — 2026-09-07 상단 4항목 요약(app/db/action_summary.py)이
# 원본에서 직접 지원방법을 보여주게 되면서 이 자리는 제거한다(중복·혼동 방지).
DETAIL_EXTRA_FIELDS = [
    ("주관기관", "주관기관"),
    ("소관기관", "소관기관"),
    ("지역", "지역"),
    ("지원분야", "지원분야_대분류"),
    ("지원분야(세부)", "지원분야_중분류"),
    ("문의처", "문의처"),
]

# 화면에 그대로 노출하기엔 기술적인 confirmation_status 값을
# 사용자가 이해하기 쉬운 문구로 바꿔서 보여주기 위한 매핑.
# 저장된 값(DB)은 그대로 두고, 표시할 때만 이 매핑을 거친다.
CONFIRMATION_DISPLAY_LABELS = {
    "확인된 사실": "확인된 사실",
    "AI 분석": "자동 계산",  # 실제로는 AI가 아니라 날짜 계산 등 규칙 기반 처리라서 오해를 막기 위해 순화
    "추정": "추정",
    "미추출": "미추출",
    "해당없음": "정보없음",
}

CONFIRMATION_BADGE_CLASS = {
    "확인된 사실": "badge-fact",
    "AI 분석": "badge-ai",
    "추정": "badge-guess",
}

# programs.source(내부 키) -> 화면에 보여줄 출처 배지 문구.
# 2026-09-07 발견: list.html/detail.html이 이 매핑 없이 "기업마당"을
# 하드코딩하고 있어서, K-Startup 출처 레코드도 화면에는 "기업마당"으로
# 잘못 표시되고 있었다(데이터 자체는 정상, 표시만 틀림). 정부24 공공서비스
# (혜택)를 붙이면서 이 매핑으로 일반화해 세 출처 모두 올바르게 표시한다.
SOURCE_DISPLAY_LABELS = {
    "bizinfo": "기업마당",
    "kstartup": "창업진흥원(K-Startup)",
    "public_benefits": "정부24 혜택",
    "kocca": "한국콘텐츠진흥원",
    "enara": "e나라도움 국고보조금",
}

# programs.status_computed에 저장된 내부 값 중, 사용자에게는 더 쉬운
# 말로 바꿔 보여줘야 하는 것들. 저장된 값 자체(필터링에 쓰이는 값)는
# 바꾸지 않고 화면 표시만 바꾼다.
STATUS_DISPLAY_LABELS = {
    "비정형(원문 참조)": "상시·조건부 접수 (원문 확인 필요)",
}
