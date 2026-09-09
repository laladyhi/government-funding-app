"""e나라도움 원본을 운영 DB에 적재한다. 기본은 dry-run이다."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "collector" / "raw" / "enara" / "items"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from load_standard_program import load_standard_program  # noqa: E402
sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.enara_adapter import EnaraAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="미리보기/시험용 최대 건수(0은 전체)")
    args = parser.parse_args()
    entries = []
    for directory in sorted(RAW_DIR.iterdir()) if RAW_DIR.exists() else []:
        paths = sorted(directory.glob("*.json"))
        if paths:
            path = paths[-1]
            entries.append((path, json.loads(path.read_bytes().decode("utf-8"))))
    if not entries:
        print("[결과] 실패 — e나라도움 원본이 없습니다. 먼저 collector/fetch_enara.py를 실행하세요.")
        return 1
    adapter = EnaraAdapter()
    conn = get_connection()
    converted = []
    if args.limit > 0:
        entries = entries[: args.limit]
    for path, raw in entries:
        program = adapter.to_standard_program(raw)
        program.content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        program.collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        converted.append((program, raw))
    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, raw in converted:
        existing = conn.execute(
            "SELECT latest_raw_hash FROM programs WHERE source = ? AND source_item_id = ?",
            (program.source, program.source_program_id),
        ).fetchone()
        outcome = "unchanged" if existing and existing[0] == program.content_hash else ("updated" if existing else "inserted")
        outcomes[outcome] += 1
        print(f"  - {program.source_program_id}: {outcome} — {program.title[:80]}")
    if not args.commit:
        print(f"[DRY-RUN] {len(converted)}건 미리보기만 했습니다. 운영 DB는 변경하지 않았습니다.")
        return 0
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"govfunding_before_enara_load_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    shutil.copyfile(DB_PATH, backup)
    for program, raw in converted:
        load_standard_program(conn, program, raw)
    conn.commit()
    print(f"[결과] e나라도움 적재 완료 — 신규 {outcomes['inserted']}건, 갱신 {outcomes['updated']}건, 변경없음 {outcomes['unchanged']}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
