"""
해시 통일 작업 검증 테스트 (재실행 가능).

pytest 등 추가 라이브러리 없이 그냥 실행할 수 있는 스크립트다.
python app/db/test_hash_consistency.py

확인하는 것:
  1. 동일 파일을 다시 처리해도 해시가 같은가 (결정성)
  2. 내용이 실제로 바뀌면 해시가 달라지는가 (민감성)
  3. 내용이 안 바뀌면(복사본) 해시가 같은가 (오탐 없음)
  4. DB 안에서 같은 원본을 가리키는 세 곳의 해시가 서로 일치하는가
     (programs.latest_raw_hash / source_documents.content_hash /
     raw_api_responses.content_hash)
  5. collector/raw 원본 파일이 이번 테스트로 인해 바뀌지 않았는가
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from load_bizinfo import RAW_ITEMS_DIR  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from fetch_and_store import compute_file_hash  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

results = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def find_sample_raw_file() -> Path:
    for item_dir in sorted(RAW_ITEMS_DIR.iterdir()):
        files = sorted(item_dir.glob("*.json"))
        if files:
            return files[-1]
    raise FileNotFoundError("샘플로 쓸 raw 파일을 찾지 못함")


def test_determinism(sample_path: Path):
    h1 = compute_file_hash(sample_path)
    h2 = compute_file_hash(sample_path)
    check(
        "1. 동일 원본 재처리 시 해시 동일(결정성)",
        h1 == h2,
        f"{h1[:16]}... == {h2[:16]}...",
    )
    return h1


def test_sensitivity(sample_path: Path, original_hash: str):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 내용이 같은 복사본 -> 해시가 같아야 함 (오탐 없음)
        unchanged_copy = tmp_dir / "unchanged.json"
        shutil.copyfile(sample_path, unchanged_copy)
        unchanged_hash = compute_file_hash(unchanged_copy)
        check(
            "2. 내용이 같은 복사본은 해시도 동일 (오탐 없음)",
            unchanged_hash == original_hash,
        )

        # 내용을 한 글자 바꾼 복사본 -> 해시가 달라져야 함
        original_bytes = sample_path.read_bytes()
        changed_bytes = original_bytes.replace(b'"pblancNm"', b'"pblancNmX"', 1)
        if changed_bytes == original_bytes:
            # 혹시 해당 필드가 없는 파일이면, 그냥 마지막 바이트 하나를 바꿔서 테스트
            changed_bytes = original_bytes[:-1] + bytes([original_bytes[-1] ^ 0x01])
        changed_copy = tmp_dir / "changed.json"
        changed_copy.write_bytes(changed_bytes)
        changed_hash = compute_file_hash(changed_copy)
        check(
            "3. 내용이 실제로 바뀌면 해시도 달라짐 (민감성)",
            changed_hash != original_hash,
        )


def test_db_cross_consistency():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT p.id, p.source_item_id, p.latest_raw_hash AS program_hash,
               sd.content_hash AS webpage_doc_hash,
               (SELECT content_hash FROM raw_api_responses
                  WHERE source_item_id = p.source_item_id AND response_type = 'item'
                  ORDER BY id DESC LIMIT 1) AS raw_item_hash
        FROM programs p
        JOIN source_documents sd ON sd.program_id = p.id AND sd.document_type = '웹페이지'
        """
    ).fetchall()

    mismatches = [
        dict(r) for r in rows
        if not (r["program_hash"] == r["webpage_doc_hash"] == r["raw_item_hash"])
    ]
    check(
        f"4. DB 내 3개 해시(programs/source_documents/raw_api_responses) 전부 일치",
        len(mismatches) == 0,
        f"검사 {len(rows)}건 중 불일치 {len(mismatches)}건",
    )
    if mismatches:
        for m in mismatches:
            print("   불일치:", m)


def test_raw_files_untouched(before_snapshot: dict):
    raw_dir = PROJECT_ROOT / "collector" / "raw"
    after_snapshot = {
        str(p): p.stat().st_mtime_ns for p in sorted(raw_dir.rglob("*.json"))
    }
    check(
        "5. collector/raw 원본 파일이 테스트 중 변경되지 않음",
        before_snapshot == after_snapshot,
        f"파일 {len(after_snapshot)}개 비교",
    )


def main() -> int:
    raw_dir = PROJECT_ROOT / "collector" / "raw"
    before_snapshot = {
        str(p): p.stat().st_mtime_ns for p in sorted(raw_dir.rglob("*.json"))
    }

    sample_path = find_sample_raw_file()
    print(f"샘플 파일: {sample_path.relative_to(PROJECT_ROOT)}\n")

    original_hash = test_determinism(sample_path)
    test_sensitivity(sample_path, original_hash)
    test_db_cross_consistency()
    test_raw_files_untouched(before_snapshot)

    print()
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"[요약] {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
