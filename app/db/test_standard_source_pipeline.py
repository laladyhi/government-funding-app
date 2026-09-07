"""
KOCCA 어댑터 파이프라인을 픽스처(가상 데이터)만으로 검증한다.

K-Startup은 2026-09-04 실제 API 테스트 이후 어댑터가 실제 필드 기준으로
재작성되어, 이 파일이 쓰던 옛 가상(mock) 픽스처(camelCase 추정 필드명)와
더 이상 맞지 않는다. K-Startup 검증은
app/db/test_kstartup_real_pipeline.py(실제 캡처 응답 fixture 사용)에서
별도로 한다.

이 테스트는:
  - 실제 API를 절대 호출하지 않는다 (fetch_list()는 어댑터 안에서 이미
    막혀 있고, 이 테스트는 fetch_list()를 부르지도 않는다).
  - collector/fixtures/*.json 만 읽는다.
  - 운영 중인 app/data/govfunding.sqlite3 에는 아무것도 쓰지 않는다 —
    임시 SQLite DB를 새로 만들어 그 안에서만 테스트한다. 그래서 실제
    화면에 가짜 테스트 공고가 섞여 보일 일이 없다.

실행: python app/db/test_standard_source_pipeline.py
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
FIXTURES_DIR = PROJECT_ROOT / "collector" / "fixtures"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_standard_program import load_standard_program  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.kocca_adapter import KoccaAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

results = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def build_temp_db() -> sqlite3.Connection:
    """운영 DB와 완전히 분리된 임시 DB에 같은 마이그레이션을 적용한다."""
    tmp_path = Path(tempfile.mkstemp(suffix=".sqlite3")[1])
    conn = sqlite3.connect(tmp_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(migration_file.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def fixture_item_hash(item: dict) -> str:
    """
    픽스처 전용 해시. 실제 수집 데이터는 raw-data-hash-policy.md에 따라
    '저장된 파일의 바이트'를 해싱하지만, 픽스처는 파일 하나에 여러 항목이
    배열로 들어있어 항목별 파일이 없다. 그래서 여기서는 항목의 JSON
    내용 자체를 해싱한다 — 결정성(같은 내용 -> 같은 해시)은 동일하게
    보장되지만, 실제 운영 파이프라인의 해시 값과는 계산 대상이 다르다는
    점을 분명히 한다.
    """
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    data = json.loads(path.read_text(encoding="utf-8"))
    check(f"{name}: _is_real_data가 false로 명시됨 (가상 데이터 확인)", data.get("_is_real_data") is False)
    return data


def run_adapter_pipeline(adapter, fixture_data: dict, conn) -> dict:
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0}
    converted = []

    for raw_item in fixture_data["items"]:
        program = adapter.to_standard_program(raw_item)
        program.content_hash = fixture_item_hash(raw_item)
        program.collected_at = collected_at
        converted.append(program)
        outcome = load_standard_program(conn, program, raw_item)
        outcomes[outcome] += 1

    conn.commit()
    return {"converted": converted, "outcomes": outcomes}


def main() -> int:
    # 운영 DB 건수는 다른 승인된 작업(예: K-Startup 5건 적재)으로 계속
    # 늘어날 수 있으므로, 특정 숫자를 하드코딩하지 않고 "이 테스트
    # 실행 전후로 안 바뀌었는가"만 비교한다.
    baseline_conn = sqlite3.connect(PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3")
    baseline_total = baseline_conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    baseline_conn.close()

    conn = build_temp_db()

    print("=== KOCCA 픽스처 파이프라인 ===")
    kocca_fixture = load_fixture("kocca_sample_response.json")
    kocca_result = run_adapter_pipeline(KoccaAdapter(), kocca_fixture, conn)
    check("KOCCA: 3건 입력 중 신규 2건 + 중복 1건 스킵", kocca_result["outcomes"] == {"inserted": 2, "updated": 0, "unchanged": 1},
          str(kocca_result["outcomes"]))

    no_date_program = next(p for p in kocca_result["converted"] if p.source_program_id == "KOCCA-FIXTURE-002")
    check("KOCCA: 날짜 없는 항목의 application_start/end가 None (날짜를 지어내지 않음)",
          no_date_program.application_start is None and no_date_program.application_end is None)

    print()
    print("=== DB 반영 결과 확인 (임시 DB) ===")
    total_programs = conn.execute("SELECT COUNT(*) c FROM programs").fetchone()["c"]
    check("KOCCA 프로그램 2건만 적재됨 (중복 1건은 제외)", total_programs == 2, f"실제: {total_programs}")

    sources = {r["source"] for r in conn.execute("SELECT DISTINCT source FROM programs")}
    check("source 컬럼에 kocca만 존재", sources == {"kocca"}, str(sources))

    # 출처 저장 확인 (source_url이 비어있지 않고, source_documents에 반영됐는지)
    doc_count = conn.execute("SELECT COUNT(*) c FROM source_documents WHERE document_type='웹페이지'").fetchone()["c"]
    check("웹페이지 출처 문서가 프로그램 수만큼 저장됨", doc_count == 2, f"실제: {doc_count}")

    print()
    print("=== 운영 DB 무영향 확인 ===")
    prod_conn = sqlite3.connect(PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3")
    prod_count = prod_conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    fixture_titles_in_prod = prod_conn.execute(
        "SELECT COUNT(*) FROM programs WHERE source = 'kocca'"
    ).fetchone()[0]
    check("운영 DB의 programs 건수가 테스트 실행 전후로 그대로임(하드코딩 아님)",
          prod_count == baseline_total, f"실행 전: {baseline_total}, 실행 후: {prod_count}")
    check("운영 DB에 kocca 테스트 데이터가 섞이지 않음", fixture_titles_in_prod == 0, f"실제: {fixture_titles_in_prod}")
    prod_conn.close()

    print()
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"[요약] {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
