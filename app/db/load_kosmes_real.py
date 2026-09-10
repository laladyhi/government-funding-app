"""KOSMES 원문을 기존 표준 프로그램 DB에 적재한다."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "kosmes" / "items"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_standard_program import load_standard_program  # noqa: E402
from query import get_connection  # noqa: E402
sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.kosmes_adapter import KosmesAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    entries = []
    for item_dir in sorted(RAW_ITEMS_DIR.iterdir()) if RAW_ITEMS_DIR.exists() else []:
        paths = sorted(item_dir.glob("*.json"))
        if paths:
            path = paths[-1]
            entries.append((path, json.loads(path.read_text(encoding="utf-8"))))
    if not entries:
        print("[결과] 실패 - KOSMES 원본이 없습니다.")
        return 1
    adapter = KosmesAdapter()
    conn = get_connection()
    converted = []
    for path, raw_item in entries:
        program = adapter.to_standard_program(raw_item)
        program.content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        converted.append((program, raw_item))
    if not args.commit:
        print(f"[DRY-RUN] KOSMES {len(converted)}건 미리보기만 했습니다.")
        return 0
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DB_PATH, BACKUP_DIR / f"govfunding_before_kosmes_{datetime.now():%Y%m%d_%H%M%S}.sqlite3")
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, raw_item in converted:
        counts[load_standard_program(conn, program, raw_item)] += 1
    conn.commit()
    print(f"[결과] KOSMES 적재 완료 - 신규 {counts['inserted']}건, 갱신 {counts['updated']}건, 변경없음 {counts['unchanged']}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
