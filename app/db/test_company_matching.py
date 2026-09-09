"""
회사-지원사업 매칭 엔진을 테스트용 회사 프로필로 미리보기만 하는 스크립트.

이 스크립트는:
  - AI/외부 API를 전혀 호출하지 않는다(app/db/company_matching.py가
    순수 규칙 기반이므로 애초에 호출할 대상이 없음).
  - 운영 DB의 programs/program_fields 등 기존 지원사업 표는 전혀
    쓰지 않는다(읽기만 함) — 실행 전후 건수가 같은지 직접 확인한다.
  - company_profiles 표에 "[테스트]"로 시작하는 이름의 테스트 프로필
    1건만 추가한다 — 이것이 이 스크립트가 만드는 유일한 쓰기 작업이다.

실행: python app/db/test_company_matching.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from company_matching import match_company_to_all_programs, VERDICT_GOOD, VERDICT_REVIEW, VERDICT_MISMATCH  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TEST_COMPANY_NAME = "[테스트] 미리보기용 회사"


def main() -> int:
    conn = get_connection()

    before_programs = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    before_fields = conn.execute("SELECT COUNT(*) FROM program_fields").fetchone()[0]

    # 이미 같은 이름의 테스트 프로필이 있으면 새로 만들지 않고 재사용한다
    # (재실행해도 안전하게).
    existing = conn.execute(
        "SELECT id FROM company_profiles WHERE name = ?", (TEST_COMPANY_NAME,)
    ).fetchone()
    if existing:
        company_id = existing[0]
        print(f"[정보] 기존 테스트 프로필 재사용 (id={company_id})")
    else:
        cur = conn.execute(
            """
            INSERT INTO company_profiles (
              name, region, industry, founded_date, business_age_years,
              employee_count, revenue_range, company_type, exports, rnd,
              desired_fields
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                TEST_COMPANY_NAME, "경기", "제조업", "2023-03-01", None,
                7, "1억~10억", "소상공인", "아니오", "아니오",
                "소상공인, 디지털 전환",
            ),
        )
        conn.commit()
        company_id = cur.lastrowid
        print(f"[정보] 테스트 프로필 신규 생성 (id={company_id})")

    company = dict(conn.execute(
        "SELECT * FROM company_profiles WHERE id = ?", (company_id,)
    ).fetchone())

    print("\n=== 테스트 회사 프로필 ===")
    for key in ("name", "region", "industry", "founded_date", "employee_count",
                "revenue_range", "company_type", "exports", "rnd", "desired_fields"):
        print(f"  {key}: {company.get(key)}")

    print(f"\n[정보] 운영 DB의 지원사업 {before_programs}건 전체를 대상으로 매칭을 실행합니다...")
    results = match_company_to_all_programs(conn, company)

    counts = {VERDICT_GOOD: 0, VERDICT_REVIEW: 0, VERDICT_MISMATCH: 0}
    for r in results:
        counts[r["verdict"]] += 1

    print("\n=== 매칭 결과 요약 ===")
    print(f"  전체 대상: {len(results)}건")
    for verdict, count in counts.items():
        print(f"  {verdict}: {count}건")

    print(f"\n=== '{VERDICT_GOOD}' 상위 5건 미리보기 ===")
    good_examples = [r for r in results if r["verdict"] == VERDICT_GOOD][:5]
    if not good_examples:
        print("  (해당 없음)")
    for r in good_examples:
        print(f"\n  - [{r['source']}] {r['title']}")
        for dim_key, (verdict, detail) in r["dimensions"].items():
            print(f"      {dim_key}: {verdict} — {detail}")
        if r["needs_review"]:
            print(f"      >> 확인이 필요한 조건: {', '.join(r['needs_review'])}")

    print(f"\n=== '{VERDICT_MISMATCH}' 3건 미리보기(있는 경우) ===")
    mismatch_examples = [r for r in results if r["verdict"] == VERDICT_MISMATCH][:3]
    if not mismatch_examples:
        print("  (해당 없음)")
    for r in mismatch_examples:
        print(f"\n  - [{r['source']}] {r['title']}")
        for dim_key, (verdict, detail) in r["dimensions"].items():
            if verdict == "불일치":
                print(f"      {dim_key}: {verdict} — {detail}")

    after_programs = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    after_fields = conn.execute("SELECT COUNT(*) FROM program_fields").fetchone()[0]

    print("\n=== 운영 DB 변경 여부 확인 ===")
    print(f"  programs 실행 전/후: {before_programs} / {after_programs}"
          f"  ({'변경 없음' if before_programs == after_programs else '경고: 변경됨'})")
    print(f"  program_fields 실행 전/후: {before_fields} / {after_fields}"
          f"  ({'변경 없음' if before_fields == after_fields else '경고: 변경됨'})")
    print(f"  company_profiles에 추가된 것: 테스트 프로필 1건(id={company_id})뿐")

    return 0 if before_programs == after_programs and before_fields == after_fields else 1


if __name__ == "__main__":
    sys.exit(main())
