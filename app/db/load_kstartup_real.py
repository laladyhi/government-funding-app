"""collector/raw/kstartup/items/의 최신 원본을 운영 DB에 적재한다.

기본은 dry-run이며, 실제 저장은 ``--commit``을 명시해야 한다. 네트워크는
호출하지 않고 이미 저장된 원본 파일만 읽는다.
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "kstartup" / "items"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from load_standard_program import load_standard_program  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.kstartup_adapter import KstartupAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_items() -> list[tuple[Path, dict]]:
    results = []
    if not RAW_ITEMS_DIR.exists():
        return results
    for item_dir in sorted(RAW_ITEMS_DIR.iterdir()):
        if not item_dir.is_dir():
            continue
        paths = sorted(item_dir.glob("*.json"))
        if paths:
            path = paths[-1]
            results.append((path, json.loads(path.read_bytes().decode("utf-8"))))
    return results


def backup_db() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"govfunding_before_kstartup_load_{stamp}.sqlite3"
    shutil.copyfile(DB_PATH, path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="운영 DB에 실제로 적재합니다.")
    args = parser.parse_args()
    entries = latest_items()
    if not entries:
        print(f"[결과] 실패 — 원본 파일이 없습니다: {RAW_ITEMS_DIR}")
        print("먼저 python collector/fetch_kstartup.py --full 을 실행하세요.")
        return 1

    adapter = KstartupAdapter()
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    converted = []
    for path, raw_item in entries:
        program = adapter.to_standard_program(raw_item)
        program.content_hash = file_hash(path)
        program.collected_at = collected_at
        converted.append((program, raw_item, path))

    conn = get_connection()
    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, _, path in converted:
        row = conn.execute(
            "SELECT latest_raw_hash FROM programs WHERE source = ? AND source_item_id = ?",
            (program.source, program.source_program_id),
        ).fetchone()
        outcome = "unchanged" if row and row[0] == program.content_hash else ("updated" if row else "inserted")
        outcomes[outcome] += 1
        print(f"  - {program.source_program_id}: {outcome} — {program.title[:80]}")

    if not args.commit:
        print(f"[DRY-RUN] {len(converted)}건을 미리보기만 했습니다. 운영 DB는 변경하지 않았습니다.")
        return 0

    backup_path = backup_db()
    print(f"[정보] 적재 전 백업 완료: {backup_path}")
    for program, raw_item, _ in converted:
        load_standard_program(conn, program, raw_item)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    print(f"[결과] 적재 완료 — 신규 {outcomes['inserted']}건, 갱신 {outcomes['updated']}건, 변경없음 {outcomes['unchanged']}건")
    print(f"[정보] programs 총 건수: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
