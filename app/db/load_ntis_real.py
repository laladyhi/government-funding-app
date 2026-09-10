"""collector/raw/ntis/items의 최신 원문을 운영 DB에 적재한다."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "ntis" / "items"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_standard_program import load_standard_program  # noqa: E402
from query import get_connection  # noqa: E402
sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.ntis_adapter import NtisAdapter  # noqa: E402


def latest_items():
    results = []
    if not RAW_ITEMS_DIR.exists():
        return results
    for item_dir in sorted(RAW_ITEMS_DIR.iterdir()):
        if not item_dir.is_dir():
            continue
        paths = sorted(item_dir.glob("*.json"))
        if paths:
            path = paths[-1]
            results.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="운영 DB에 실제로 적재합니다.")
    args = parser.parse_args()
    entries = latest_items()
    if not entries:
        print(f"[결과] 실패 - NTIS 원본이 없습니다: {RAW_ITEMS_DIR}")
        print("먼저 python collector/fetch_ntis.py --keyword 창업 을 실행하세요.")
        return 1
    adapter = NtisAdapter()
    converted = []
    for path, raw_item in entries:
        program = adapter.to_standard_program(raw_item)
        program.content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        converted.append((program, raw_item))
    conn = get_connection()
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, _ in converted:
        row = conn.execute(
            "SELECT latest_raw_hash FROM programs WHERE source = ? AND source_item_id = ?",
            (program.source, program.source_program_id),
        ).fetchone()
        outcome = "unchanged" if row and row[0] == program.content_hash else ("updated" if row else "inserted")
        counts[outcome] += 1
    if not args.commit:
        print(f"[DRY-RUN] NTIS {len(converted)}건 미리보기만 했습니다. DB는 변경하지 않았습니다.")
        return 0
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"govfunding_before_ntis_load_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
    shutil.copyfile(DB_PATH, backup)
    for program, raw_item in converted:
        load_standard_program(conn, program, raw_item)
        program_id = conn.execute(
            "SELECT id FROM programs WHERE source = ? AND source_item_id = ?",
            (program.source, program.source_program_id),
        ).fetchone()[0]
        source_document_id = conn.execute(
            "SELECT id FROM source_documents WHERE program_id = ? ORDER BY id DESC LIMIT 1",
            (program_id,),
        ).fetchone()[0]
        extra_fields = [
            ("과제번호", raw_item.get("project_number")),
            ("연구책임자", raw_item.get("manager")),
            ("연구개발목표", raw_item.get("goal")),
            ("연구개발내용", raw_item.get("abstract")),
            ("기대효과", raw_item.get("effect")),
            ("핵심키워드", raw_item.get("keyword_ko")),
            ("연구비", raw_item.get("government_funds")),
            ("총연구비", raw_item.get("total_funds")),
            ("소관기관", raw_item.get("ministry")),
        ]
        for field_name, value in extra_fields:
            conn.execute(
                """INSERT INTO program_fields
                   (program_id, field_name, field_value, confirmation_status,
                    source_document_id, section_text, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (program_id, field_name, value, "확인된 사실" if value else "미추출",
                 source_document_id, "NTIS API 원문 필드", program.collected_at),
            )
    conn.commit()
    print(f"[결과] NTIS 적재 완료 - 신규 {counts['inserted']}건, 갱신 {counts['updated']}건, 변경없음 {counts['unchanged']}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
