"""collector/raw/kocca/items의 최신 원본을 KOCCA 프로그램으로 적재한다."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "collector" / "raw" / "kocca" / "items"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from load_standard_program import load_standard_program  # noqa: E402
sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.kocca_adapter import KoccaAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    entries = []
    for directory in sorted(RAW_DIR.iterdir()) if RAW_DIR.exists() else []:
        files = sorted(directory.glob("*.json"))
        if files:
            path = files[-1]
            entries.append((path, json.loads(path.read_bytes().decode("utf-8"))))
    if not entries:
        print("[결과] 실패 — KOCCA 원본이 없습니다. 먼저 collector/fetch_kocca.py를 실행하세요.")
        return 1
    adapter = KoccaAdapter()
    conn = get_connection()
    converted = []
    for path, raw in entries:
        program = adapter.to_standard_program(raw)
        program.content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        program.collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        converted.append((program, raw))
    if not args.commit:
        print(f"[DRY-RUN] KOCCA {len(converted)}건 미리보기만 했습니다. DB는 변경하지 않았습니다.")
        return 0
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"govfunding_before_kocca_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    shutil.copyfile(DB_PATH, backup)
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, raw in converted:
        outcome = load_standard_program(conn, program, raw)
        counts[outcome] += 1
    conn.commit()
    print(f"[결과] KOCCA 적재 완료 — 신규 {counts['inserted']}건, 갱신 {counts['updated']}건, 변경없음 {counts['unchanged']}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
