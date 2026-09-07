"""
정부24 공공서비스(혜택) — 실제 수집된 원본(collector/raw/public_benefits/items/)을
운영 DB 스키마 기준으로 미리보기/적재하는 스크립트.

기본은 항상 dry-run(미리보기)이다 — 아무것도 저장하지 않는다.
실제로 운영 DB(app/data/govfunding.sqlite3)에 적재하려면 반드시
--commit 옵션을 명시해야 한다. 이 스크립트는 네트워크를 호출하지
않는다 — collector/fetch_public_benefits.py가 이미 저장해 둔 원본
파일만 읽는다(먼저 그 스크립트를 실행해 원본을 받아둬야 한다).

수행 내용:
  1. collector/raw/public_benefits/items/<서비스ID>/ 아래 각 폴더에서
     가장 최근 파일을 하나씩 읽는다 (서비스ID당 최신 스냅샷 1건).
  2. 저장된 파일 "바이트 자체"로 SHA-256 해시를 계산한다
     (docs/raw-data-hash-policy.md 기준 — 재직렬화하지 않음).
  3. PublicBenefitsAdapter.to_standard_program()으로 표준 구조 변환.
  4. 운영 DB(읽기 전용 조회)를 기준으로 "적재하면 무엇이 일어날지"를
     미리 계산한다 (신규/갱신/변경없음) — dry-run에서는 실제로 쓰지 않는다.
  5. 기존 기업마당·K-Startup 프로그램과 제목 기준 중복 후보가 있는지 확인한다.

사용법:
  python app/db/load_public_benefits_real.py            # 미리보기만 (기본)
  python app/db/load_public_benefits_real.py --commit    # 실제 운영 DB에 적재
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "public_benefits" / "items"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402  (운영 DB용, row_factory 적용됨)
from load_standard_program import load_standard_program  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.public_benefits_adapter import PublicBenefitsAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def compute_file_hash(path: Path) -> str:
    """docs/raw-data-hash-policy.md 기준 — 저장된 파일의 바이트 그대로 해시."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_latest_raw_items() -> list:
    """서비스ID 폴더마다 가장 최근(파일명 기준) 스냅샷 1건씩만 읽는다."""
    results = []
    if not RAW_ITEMS_DIR.exists():
        return results
    for service_dir in sorted(RAW_ITEMS_DIR.iterdir()):
        if not service_dir.is_dir():
            continue
        snapshot_files = sorted(service_dir.glob("*.json"))
        if not snapshot_files:
            continue
        latest_path = snapshot_files[-1]
        raw_item = json.loads(latest_path.read_bytes().decode("utf-8"))
        results.append((latest_path, raw_item))
    return results


def backup_db() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"govfunding_before_public_benefits_load_{ts}.sqlite3"
    shutil.copyfile(DB_PATH, backup_path)
    return backup_path


def preview_outcome(conn, program) -> str:
    """load_standard_program()과 동일한 판단 로직을, 쓰지 않고 미리 계산만 한다."""
    existing = conn.execute(
        "SELECT id, latest_raw_hash FROM programs WHERE source = ? AND source_item_id = ?",
        (program.source, program.source_program_id),
    ).fetchone()
    if existing and existing["latest_raw_hash"] == program.content_hash and program.content_hash:
        return "unchanged"
    if existing:
        return "updated"
    return "inserted"


def find_title_overlaps(conn, title: str) -> list:
    core_title = title.replace("[가상데이터] ", "")[:10]
    rows = conn.execute(
        "SELECT title, source FROM programs WHERE source IN ('bizinfo', 'kstartup') AND title LIKE ?",
        (f"%{core_title}%",),
    ).fetchall()
    return [(r["title"], r["source"]) for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true",
        help="실제로 운영 DB에 적재한다. 지정하지 않으면 미리보기만 하고 아무것도 저장하지 않는다.",
    )
    args = parser.parse_args()

    raw_entries = load_latest_raw_items()
    if not raw_entries:
        print(f"[결과] 실패 — 읽을 원본 파일이 없습니다: {RAW_ITEMS_DIR}")
        print("먼저 python collector/fetch_public_benefits.py 를 실행해 원본을 받아두세요.")
        return 1

    adapter = PublicBenefitsAdapter()
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    converted = []
    for path, raw_item in raw_entries:
        program = adapter.to_standard_program(raw_item)
        program.content_hash = compute_file_hash(path)
        program.collected_at = collected_at
        converted.append((program, raw_item, path))

    conn = get_connection()  # 읽기 전용 조회에만 사용 (dry-run에서는 commit 안 함)

    print(f"=== 변환 결과 미리보기 ({len(converted)}건) ===\n")
    overlap_found = False
    for program, raw_item, path in converted:
        outcome = preview_outcome(conn, program)
        overlaps = find_title_overlaps(conn, program.title)
        print(f"  - source_program_id={program.source_program_id}  title={program.title!r}")
        print(f"    organization={program.organization!r}")
        print(f"    application_period={program.application_start}~{program.application_end}  (원문: {program.application_period_raw!r})")
        print(f"    content_hash={program.content_hash}")
        print(f"    원본 파일: {path}")
        print(f"    [미리보기] 적재하면: {outcome}")
        if overlaps:
            overlap_found = True
            print(f"    [주의] 기업마당·K-Startup과 제목 유사 후보: {overlaps}")
        else:
            print("    기업마당·K-Startup과 제목 중복 후보 없음")
        print()

    if not args.commit:
        print(f"[DRY-RUN] 실제로 저장하지 않았습니다 ({len(converted)}건 미리보기만).")
        print("[DRY-RUN] 운영 DB에 적재하려면 --commit 옵션을 붙여 다시 실행하세요 (사용자 별도 승인 필요).")
        prod_total = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
        prod_pb = conn.execute("SELECT COUNT(*) FROM programs WHERE source='public_benefits'").fetchone()[0]
        print(f"[확인] 운영 DB programs 총 건수(변경 없음): {prod_total} (public_benefits: {prod_pb})")
        if overlap_found:
            print("[참고] 제목 유사 후보가 발견되었습니다 — 실제 중복인지는 사람이 확인해야 합니다(자동 판정 아님).")
        return 0

    # --commit 모드: 실제로 저장한다.
    backup_path = backup_db()
    print(f"[정보] 적재 전 운영 DB 백업 완료: {backup_path}")

    before_count = conn.execute("SELECT COUNT(*) c FROM programs").fetchone()["c"]
    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, raw_item, path in converted:
        outcome = load_standard_program(conn, program, raw_item)
        outcomes[outcome] += 1
        print(f"  - source_program_id={program.source_program_id}: {outcome}")
    conn.commit()

    after_count = conn.execute("SELECT COUNT(*) c FROM programs").fetchone()["c"]
    print(f"\n[결과] 신규 {outcomes['inserted']}건, 갱신 {outcomes['updated']}건, 변경없음 {outcomes['unchanged']}건")
    print(f"[정보] programs 총 건수: {before_count} -> {after_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
