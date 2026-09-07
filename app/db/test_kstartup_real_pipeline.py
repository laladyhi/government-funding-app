"""
K-Startup 실제 캡처 응답(5건, fixture)만으로 어댑터 변환을 검증한다.

이 테스트는:
  - 네트워크를 호출하지 않는다 — collector/fixtures/kstartup_real_sample_20260904.json
    (2026-09-04에 이미 캡처해둔 실제 응답)만 읽는다.
  - 운영 DB(app/data/govfunding.sqlite3)에는 아무것도 쓰지 않는다 — 임시
    DB에서만 적재를 검증한다. 운영 DB 적재는 별도 승인 후
    app/db/load_kstartup_real_sample.py --commit 으로만 한다.
  - 변환 결과를 필드별 출처/확인상태와 함께 화면에 출력한다.

실행: python app/db/test_kstartup_real_pipeline.py
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
FIXTURE_PATH = PROJECT_ROOT / "collector" / "fixtures" / "kstartup_real_sample_20260904.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_standard_program import load_standard_program  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.kstartup_adapter import KstartupAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

results = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def fixture_item_hash(item: dict) -> str:
    """
    fixture 전용 해시(파일 하나에 여러 항목이 배열로 있어 항목별 파일이
    없으므로, 항목의 JSON 내용을 해싱한다). 운영 raw 파일의 해시 정책
    (raw-data-hash-policy.md, 파일 바이트 기준)과는 계산 대상이 다르다는
    점을 명시한다.
    """
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_field_report(program, raw_item: dict) -> list:
    """(필드명, 값, 확인상태, 비고) 목록 — 사람이 눈으로 검증하기 위한 표."""
    rows = [
        ("source", program.source, "확인된 사실", "고정값(어댑터의 source_key)"),
        ("source_program_id", program.source_program_id, "확인된 사실",
         f"raw.pbanc_sn={raw_item.get('pbanc_sn')!r} 사용 (raw.id={raw_item.get('id')!r}는 페이지 순번이라 미사용)"),
        ("title", program.title, "확인된 사실" if program.title else "미추출", "raw.biz_pbanc_nm"),
        ("organization", program.organization,
         "확인된 사실" if program.organization else "미추출",
         f"raw.sprv_inst={raw_item.get('sprv_inst')!r}"
         + ("" if program.organization else " — 일반 유형 표현이라 기관명으로 저장하지 않음(기관명 미확인)")),
        ("application_start", program.application_start,
         "확인된 사실" if program.application_start else "미추출",
         f"raw.pbanc_rcpt_bgng_dt={raw_item.get('pbanc_rcpt_bgng_dt')!r} (YYYYMMDD로 파싱)"),
        ("application_end", program.application_end,
         "확인된 사실" if program.application_end else "미추출",
         f"raw.pbanc_rcpt_end_dt={raw_item.get('pbanc_rcpt_end_dt')!r} (YYYYMMDD로 파싱)"),
        ("target", program.target_raw, "확인된 사실" if program.target_raw else "미추출",
         "raw.aply_trgt + raw.aply_trgt_ctnt"),
        ("source_url", program.source_url, "확인된 사실" if program.source_url else "미추출", "raw.detl_pg_url"),
        ("attachment_urls", program.attachment_urls, "해당없음",
         "API 응답에 첨부파일 필드 자체가 없음을 실제 호출로 확인함 — 임의로 만들지 않음"),
        ("collected_at", program.collected_at, "확인된 사실", "자동 기록(테스트 실행 시각)"),
        ("content_hash", program.content_hash, "확인된 사실", "fixture 항목 JSON 기준 해시(자동 계산)"),
    ]
    return rows


def print_field_report(idx: int, program, raw_item: dict):
    print(f"\n--- 변환 결과 {idx} ---")
    for name, value, confirmation, note in build_field_report(program, raw_item):
        print(f"  {name}: {value!r}")
        print(f"    확인상태: {confirmation}  |  출처: {note}")


def build_temp_db() -> sqlite3.Connection:
    tmp_path = Path(tempfile.mkstemp(suffix=".sqlite3")[1])
    conn = sqlite3.connect(tmp_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(migration_file.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def main() -> int:
    # 운영 DB는 이후 승인된 작업(예: public_benefits 등)으로 계속 늘어날
    # 수 있으므로 절대 건수를 하드코딩하지 않고, 이 테스트 실행 전후로
    # 안 바뀌었는지만 비교한다.
    baseline_conn = sqlite3.connect(PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3")
    baseline_total = baseline_conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    baseline_kstartup = baseline_conn.execute("SELECT COUNT(*) FROM programs WHERE source='kstartup'").fetchone()[0]
    baseline_conn.close()

    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    check("fixture: _is_real_data가 true로 명시됨 (실제 캡처 데이터 확인)", fixture.get("_is_real_data") is True)
    check("fixture: 5건 포함", len(fixture["items"]) == 5, f"실제: {len(fixture['items'])}")

    adapter = KstartupAdapter()
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    converted = []
    for idx, raw_item in enumerate(fixture["items"], start=1):
        program = adapter.to_standard_program(raw_item)
        program.content_hash = fixture_item_hash(raw_item)
        program.collected_at = collected_at
        converted.append((program, raw_item))
        print_field_report(idx, program, raw_item)

    print()
    print("=== 검증 ===")

    # 1. id(페이지 순번)를 공고ID로 쓰지 않았는지
    id_used_as_key = any(
        program.source_program_id == str(raw_item.get("id"))
        and str(raw_item.get("id")) != str(raw_item.get("pbanc_sn"))
        for program, raw_item in converted
    )
    check("최상위 'id'(페이지 순번)를 공고 ID로 사용하지 않음", not id_used_as_key)
    check(
        "source_program_id가 전부 pbanc_sn과 일치",
        all(p.source_program_id == str(r["pbanc_sn"]) for p, r in converted),
    )

    # 2~3. 날짜(YYYYMMDD) 파싱 + 실패 시 미추출
    all_dates_parsed = all(p.application_start and p.application_end for p, r in converted)
    check("5건 전부 YYYYMMDD 날짜가 정상 파싱됨(이번 fixture는 전부 정상 날짜)", all_dates_parsed)
    check(
        "파싱된 날짜가 'YYYY-MM-DD' 형식(대시 포함)",
        all(len(p.application_start) == 10 and p.application_start[4] == "-" for p, r in converted),
    )

    # 4. 첨부파일 URL을 임의로 만들지 않았는지
    check("5건 전부 attachment_urls가 빈 리스트", all(p.attachment_urls == [] for p, r in converted))

    # 5~6. sprv_inst가 일반 표현이면 기관명으로 안 쓰고 미확인 처리
    generic_org_cases = [(p, r) for p, r in converted if r.get("sprv_inst") in ("공공기관", "민간", "기타")]
    check(
        "sprv_inst가 '공공기관'/'민간'인 항목은 organization이 None(기관명 미확인)",
        all(p.organization is None for p, r in generic_org_cases),
        f"해당 항목 {len(generic_org_cases)}건 확인",
    )

    # content_hash 결정성 + 항목별 상이함
    rehash_first = fixture_item_hash(converted[0][1])
    check("같은 항목을 다시 해싱해도 동일한 해시(결정성)", rehash_first == converted[0][0].content_hash)
    all_hashes = {p.content_hash for p, r in converted}
    check("5건의 content_hash가 서로 다름(내용이 다르면 해시도 다름)", len(all_hashes) == 5)

    # 임시 DB 적재 테스트 (운영 DB 아님)
    conn = build_temp_db()
    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, raw_item in converted:
        outcome = load_standard_program(conn, program, raw_item)
        outcomes[outcome] += 1
    conn.commit()
    check("임시 DB에 5건 전부 신규 적재됨", outcomes == {"inserted": 5, "updated": 0, "unchanged": 0}, str(outcomes))

    temp_total = conn.execute("SELECT COUNT(*) c FROM programs WHERE source='kstartup'").fetchone()["c"]
    check("임시 DB의 kstartup 프로그램 수 = 5", temp_total == 5, f"실제: {temp_total}")

    # 운영 DB 무영향 확인
    prod_conn = sqlite3.connect(PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3")
    prod_kstartup = prod_conn.execute("SELECT COUNT(*) FROM programs WHERE source='kstartup'").fetchone()[0]
    prod_total = prod_conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    check("운영 DB의 kstartup 건수가 이 테스트 실행으로 안 늘어남(이 테스트는 적재하지 않음)",
          prod_kstartup == baseline_kstartup, f"실행 전: {baseline_kstartup}, 실행 후: {prod_kstartup}")
    check("운영 DB의 programs 총 건수가 이 테스트 실행 전후로 그대로임(하드코딩 아님)",
          prod_total == baseline_total, f"실행 전: {baseline_total}, 실행 후: {prod_total}")
    prod_conn.close()

    print()
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"[요약] {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
