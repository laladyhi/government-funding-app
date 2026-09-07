"""
일회성 해시 재계산 스크립트 (2026-09-04).

목적: docs/raw-data-hash-policy.md 에 정한 새 기준(파일 바이트 그대로 SHA-256)
으로 이미 DB에 있는 해시 값들을 다시 계산해서 덮어쓴다.

이 스크립트가 절대 하지 않는 것:
  - collector/raw 원본 파일 내용 변경 (읽기만 함)
  - programs/organizations/program_fields 등 해시 이외의 값 변경
  - 새 행 삽입 (raw_api_responses의 page 레코드만 재계산을 위해 삭제 후
    같은 파일 내용으로 다시 만든다 — 식별할 파일 경로가 DB에 없어서
    이 방식이 가장 안전하다. item 레코드는 경로를 알 수 있어 UPDATE만 한다)
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from load_bizinfo import load_latest_raw_item_file, RAW_PAGES_DIR  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from fetch_and_store import compute_file_hash  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def rehash_programs_and_webpage_docs(conn):
    changed = []
    for p in conn.execute("SELECT id, source_item_id, latest_raw_hash FROM programs"):
        raw_path = load_latest_raw_item_file(p["source_item_id"])
        if not raw_path:
            print(f"[경고] program {p['id']} raw 파일을 찾지 못함 — 건너뜀")
            continue
        new_hash = compute_file_hash(raw_path)
        old_hash = p["latest_raw_hash"]
        conn.execute("UPDATE programs SET latest_raw_hash = ? WHERE id = ?", (new_hash, p["id"]))
        conn.execute(
            "UPDATE source_documents SET content_hash = ? WHERE program_id = ? AND document_type = '웹페이지'",
            (new_hash, p["id"]),
        )
        changed.append((p["id"], p["source_item_id"], old_hash, new_hash))
    return changed


def rehash_item_raw_responses(conn):
    changed = []
    for r in conn.execute(
        "SELECT id, source_item_id, content_hash FROM raw_api_responses WHERE response_type = 'item'"
    ):
        raw_path = load_latest_raw_item_file(r["source_item_id"])
        if not raw_path:
            continue
        new_hash = compute_file_hash(raw_path)
        old_hash = r["content_hash"]
        conn.execute("UPDATE raw_api_responses SET content_hash = ? WHERE id = ?", (new_hash, r["id"]))
        changed.append((r["source_item_id"], old_hash, new_hash))
    return changed


def rehash_page_raw_responses(conn):
    """
    page 레코드는 DB에 원본 파일 경로가 저장되어 있지 않아 어떤 DB 행이
    어떤 파일에서 왔는지 안전하게 매칭할 수 없다. raw_json 컬럼에 파일과
    동일한 내용이 텍스트로 이미 저장되어 있으므로, 그 컬럼을 기준으로
    파일을 찾아 매칭한 뒤 해시만 다시 계산한다.
    """
    changed = []
    page_files = sorted(RAW_PAGES_DIR.glob("*.json"))
    file_contents = {f: f.read_text(encoding="utf-8") for f in page_files}

    for r in conn.execute(
        "SELECT id, raw_json, content_hash FROM raw_api_responses WHERE response_type = 'page'"
    ):
        match_path = None
        for f, content in file_contents.items():
            if content == r["raw_json"]:
                match_path = f
                break
        if not match_path:
            print(f"[경고] raw_api_responses.id={r['id']} (page)에 대응하는 파일을 찾지 못함 — 건너뜀")
            continue
        new_hash = compute_file_hash(match_path)
        old_hash = r["content_hash"]
        conn.execute("UPDATE raw_api_responses SET content_hash = ? WHERE id = ?", (new_hash, r["id"]))
        changed.append((match_path.name, old_hash, new_hash))
    return changed


def main() -> int:
    conn = get_connection()

    print("=== programs.latest_raw_hash / source_documents.content_hash(웹페이지) 재계산 ===")
    prog_changes = rehash_programs_and_webpage_docs(conn)
    for pid, item_id, old, new in prog_changes:
        same = "(동일)" if old == new else "(변경됨)"
        print(f"  program {pid} [{item_id}] {same}")
        print(f"    이전: {old}")
        print(f"    이후: {new}")

    print()
    print("=== raw_api_responses(item) 재계산 ===")
    item_changes = rehash_item_raw_responses(conn)
    for item_id, old, new in item_changes:
        same = "(동일)" if old == new else "(변경됨)"
        print(f"  {item_id} {same}")
        print(f"    이전: {old}")
        print(f"    이후: {new}")

    print()
    print("=== raw_api_responses(page) 재계산 ===")
    page_changes = rehash_page_raw_responses(conn)
    for fname, old, new in page_changes:
        same = "(동일)" if old == new else "(변경됨)"
        print(f"  {fname} {same}")
        print(f"    이전: {old}")
        print(f"    이후: {new}")

    conn.commit()

    print()
    print(f"[결과] programs/웹페이지문서 {len(prog_changes)}건, item 원본 {len(item_changes)}건, "
          f"page 원본 {len(page_changes)}건의 해시를 새 기준으로 재계산했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
