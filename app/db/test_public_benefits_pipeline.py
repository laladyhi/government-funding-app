"""
정부24 공공서비스(혜택) 어댑터를 fixture(가상 값 + 실제 확인된 스키마)만으로
검증한다.

이 테스트는:
  - 실제 API를 절대 호출하지 않는다. `.env`에 PUBLIC_BENEFITS_API_KEY가
    아직 없으므로 check_readiness()가 자연스럽게 MISSING_KEY를 반환하고,
    그 상태에서 fetch_list()/fetch_detail()/fetch_support_conditions_raw()가
    정말로 requests.get을 부르지 않는지까지 직접 검증한다(요청 시
    requests.get을 일부러 "터지게" 만들어 확인한다).
  - 운영 DB(app/data/govfunding.sqlite3)에는 아무것도 쓰지 않는다 —
    임시 DB에서만 적재를 검증한다.
  - 지원조건(JA코드)이 해석되지 않고 그대로 보존되는지 확인한다.

실행: python app/db/test_public_benefits_pipeline.py
"""

import hashlib
import json
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
FIXTURE_PATH = PROJECT_ROOT / "collector" / "fixtures" / "public_benefits_sample_response.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_standard_program import load_standard_program  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.base import ReadinessStatus  # noqa: E402
from adapters import public_benefits_adapter as pba_module  # noqa: E402
from adapters.public_benefits_adapter import PublicBenefitsAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

results = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def fixture_item_hash(item: dict) -> str:
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_temp_db() -> sqlite3.Connection:
    tmp_path = Path(tempfile.mkstemp(suffix=".sqlite3")[1])
    conn = sqlite3.connect(tmp_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(migration_file.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def print_field_report(idx: int, program, raw_item: dict):
    print(f"\n--- 변환 결과 {idx} ---")
    rows = [
        ("source", program.source, "확인된 사실", "고정값"),
        ("source_program_id", program.source_program_id, "확인된 사실", f"raw.서비스ID={raw_item.get('서비스ID')!r}"),
        ("title", program.title, "확인된 사실" if program.title else "미추출", "raw.서비스명"),
        ("organization", program.organization, "확인된 사실" if program.organization else "미추출", "raw.소관기관명"),
        ("application_start", program.application_start, "확인된 사실" if program.application_start else "미추출",
         f"raw.신청기한={raw_item.get('신청기한')!r}"),
        ("application_end", program.application_end, "확인된 사실" if program.application_end else "미추출", ""),
        ("target", program.target_raw, "확인된 사실" if program.target_raw else "미추출", "raw.지원대상+선정기준+사용자구분"),
        ("source_url", program.source_url, "확인된 사실" if program.source_url else "미추출", "raw.상세조회URL"),
        ("attachment_urls", program.attachment_urls, "해당없음", "명세에 첨부파일 필드 없음(확인됨) — 임의 생성 안 함"),
        ("collected_at", program.collected_at, "확인된 사실", "자동 기록"),
        ("content_hash", program.content_hash, "확인된 사실", "fixture 항목 JSON 기준 해시(자동 계산)"),
    ]
    for name, value, confirmation, note in rows:
        print(f"  {name}: {value!r}")
        print(f"    확인상태: {confirmation}" + (f"  |  출처: {note}" if note else ""))


def main() -> int:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    check("fixture: _is_real_data가 false로 명시됨(가상 값 확인)", fixture.get("_is_real_data") is False)
    check("fixture: _schema_source에 '사용자 제공' 명시됨", "사용자 제공" in fixture.get("_schema_source", ""))
    check("fixture: 3건 포함(중복 1건 포함)", len(fixture["items"]) == 3, f"실제: {len(fixture['items'])}")

    adapter = PublicBenefitsAdapter()

    print("\n=== 1) 키가 없을 때 실제 호출을 절대 하지 않는지 검증 ===")
    # 실제 .env에 키가 있을 수도 없을 수도 있다(둘 다 정상 상황) — 이
    # 테스트는 그 현재 상태에 의존하지 않는다. check_readiness()를
    # 이 블록 안에서만 강제로 MISSING_KEY로 바꿔서, "키가 없을 때"라는
    # 상황 자체를 직접 만들어 검증한다.
    current_readiness = adapter.check_readiness()
    print(f"  (참고, 검증과 무관) 현재 .env 기준 실제 준비 상태: {current_readiness.value}")

    def _boom(*args, **kwargs):
        raise AssertionError("requests.get이 호출됨 — 키 없이 실제 호출을 시도했다는 뜻!")

    original_check_readiness = adapter.check_readiness
    original_get = pba_module.requests.get
    adapter.check_readiness = lambda: ReadinessStatus.MISSING_KEY
    pba_module.requests.get = _boom
    try:
        readiness_now = adapter.check_readiness()
        check("(모의) MISSING_KEY 상태로 강제 설정됨", readiness_now == ReadinessStatus.MISSING_KEY, str(readiness_now))
        list_result = adapter.fetch_list(page=1, page_size=5)
        detail_result = adapter.fetch_detail("PBI-FIXTURE-001")
        cond_result = adapter.fetch_support_conditions_raw("PBI-FIXTURE-001")
        check("fetch_list(): 키 없는 상황을 모의했을 때 네트워크 호출 없이 빈 리스트 반환", list_result == [])
        check("fetch_detail(): 키 없는 상황을 모의했을 때 네트워크 호출 없이 None 반환", detail_result is None)
        check("fetch_support_conditions_raw(): 키 없는 상황을 모의했을 때 네트워크 호출 없이 빈 리스트 반환", cond_result == [])
    finally:
        adapter.check_readiness = original_check_readiness
        pba_module.requests.get = original_get

    print("\n=== 2) 목록 -> StandardProgram 변환 (fixture만 사용) ===")
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    converted = []
    for idx, raw_item in enumerate(fixture["items"], start=1):
        program = adapter.to_standard_program(raw_item)
        program.content_hash = fixture_item_hash(raw_item)
        program.collected_at = collected_at
        converted.append((program, raw_item))
        print_field_report(idx, program, raw_item)

    print("\n=== 검증 ===")
    normal_case = converted[0][0]
    check("정상 신청기간(범위)이 있는 항목의 날짜가 파싱됨",
          normal_case.application_start == "2026-09-10" and normal_case.application_end == "2026-10-10")

    freeform_case = converted[1][0]
    check("'예산 소진 시까지' 같은 비정형 신청기한은 날짜를 지어내지 않음(None)",
          freeform_case.application_start is None and freeform_case.application_end is None)
    check("비정형 신청기한도 원문은 application_period_raw에 보존됨",
          freeform_case.application_period_raw == "예산 소진 시까지")

    check("모든 항목의 attachment_urls가 빈 리스트(임의 생성 없음)",
          all(p.attachment_urls == [] for p, r in converted))

    check("사용자구분이 target에 태그로 보존됨(1번째 항목)",
          "[대상구분: 소상공인]" in normal_case.target_raw)

    print("\n=== 3) 지원조건(JA코드) 원문 보존 검증 ===")
    fake_conditions_payload = {"data": fixture["support_conditions_example"]["data"]}

    def _fake_get(url, params):
        return fake_conditions_payload

    # check_readiness가 MISSING_KEY라 실제로는 _get이 호출되지 않으므로,
    # "만약 키가 있었다면 원문이 그대로 나오는가"를 별도로 확인하기 위해
    # _get만 잠깐 바꿔치기하고 readiness 검사도 우회해서 순수 반환값만 본다.
    original_check = adapter.check_readiness
    original_internal_get = adapter._get
    adapter.check_readiness = lambda: ReadinessStatus.READY
    adapter._get = _fake_get
    try:
        raw_conditions = adapter.fetch_support_conditions_raw("PBI-FIXTURE-001")
    finally:
        adapter.check_readiness = original_check
        adapter._get = original_internal_get

    check("지원조건 응답이 가공 없이 원문 그대로 반환됨(JA코드 해석 안 함)",
          raw_conditions == fixture["support_conditions_example"]["data"],
          f"반환값: {raw_conditions}")

    print("\n=== 4) 임시 DB 적재 + 중복 방지 확인 ===")
    conn = build_temp_db()
    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, raw_item in converted:
        outcome = load_standard_program(conn, program, raw_item)
        outcomes[outcome] += 1
    conn.commit()
    check("3건 입력 중 신규 2건 + 중복 1건 스킵", outcomes == {"inserted": 2, "updated": 0, "unchanged": 1}, str(outcomes))

    temp_total = conn.execute("SELECT COUNT(*) c FROM programs WHERE source='public_benefits'").fetchone()["c"]
    check("임시 DB의 public_benefits 프로그램 수 = 2 (중복 제외)", temp_total == 2, f"실제: {temp_total}")

    print("\n=== 5) 운영 DB 무영향 + 기업마당·K-Startup과 제목 중복 여부 확인 ===")
    prod_conn = sqlite3.connect(PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3")
    prod_conn.row_factory = sqlite3.Row
    prod_total = prod_conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    prod_pb = prod_conn.execute("SELECT COUNT(*) FROM programs WHERE source='public_benefits'").fetchone()[0]
    check("운영 DB의 programs 총 건수는 여전히 25건", prod_total == 25, f"실제: {prod_total}")
    check("운영 DB에 public_benefits 데이터가 섞이지 않음", prod_pb == 0, f"실제: {prod_pb}")

    overlap_titles = []
    for program, raw_item in converted:
        core_title = program.title.replace("[가상데이터] ", "")
        rows = prod_conn.execute(
            "SELECT title FROM programs WHERE title LIKE ?", (f"%{core_title[:10]}%",)
        ).fetchall()
        if rows:
            overlap_titles.append((program.title, [r["title"] for r in rows]))
    check("기존 기업마당·K-Startup 25건과 제목 기준 중복 후보 없음(참고용 확인)",
          len(overlap_titles) == 0, f"발견된 유사 제목: {overlap_titles}" if overlap_titles else "")
    prod_conn.close()

    print()
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"[요약] {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
