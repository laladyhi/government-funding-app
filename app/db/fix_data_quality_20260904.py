"""
일회성 데이터 보정 스크립트 — 2026-09-04 데이터 품질 점검 결과 반영.

이미 DB에 적재된 20건에 대해서만 보정한다. 새 API 호출은 하지 않고,
이미 디스크에 있는 collector/raw 원본만 다시 읽는다(원본 파일 자체는
수정하지 않음).

P0-1 지역 보정:
  - 제목의 '[지역]' 표기가 없는 경우 더 이상 기관명을 지역으로 쓰지 않는다.
  - 기존에 저장돼 있던 잘못된 지역 값(예: "지식재산처")은 삭제하지 않고
    program_fields에 남겨둔 채(이력 보존), 올바른 값을 새 행으로 추가한다.
    화면은 가장 최근 값을 보여주므로 결과적으로 올바른 값만 노출된다.
  - programs.region_display(목록/상세 요약에 쓰는 캐시 값)도 함께 갱신한다.

P0-2 기관명 보정:
  - "기초자치단체"/"직접수행"처럼 실제 기관을 가리키지 않는 값으로 만들어진
    organizations 행과, 거기 연결된 program_organization_roles를 제거한다.
  - program_fields의 주관기관/소관기관 원본 값은 건드리지 않는다(원본 보존).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402  (row_factory=sqlite3.Row 적용된 버전)
from load_bizinfo import load_latest_raw_item_file, NON_ORG_NAME_VALUES  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from fetch_and_store import guess_region_from_title  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def fix_regions(conn):
    changed = []
    programs = conn.execute("SELECT id, title, source_item_id FROM programs").fetchall()
    for p in programs:
        raw_path = load_latest_raw_item_file(p["source_item_id"])
        if not raw_path:
            print(f"[경고] program {p['id']} 원본 파일을 찾지 못함 — 건너뜀")
            continue
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        new_region = guess_region_from_title(raw.get("pblancNm", ""))

        old_row = conn.execute(
            """SELECT field_value FROM program_fields
               WHERE program_id = ? AND field_name = '지역'
               ORDER BY collected_at DESC LIMIT 1""",
            (p["id"],),
        ).fetchone()
        old_value = old_row["field_value"] if old_row else None

        if old_value == new_region:
            continue  # 이미 올바른 값 — 그대로 둠

        doc = conn.execute(
            """SELECT id FROM source_documents
               WHERE program_id = ? AND document_type = '웹페이지' LIMIT 1""",
            (p["id"],),
        ).fetchone()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        confirmation = "추정" if new_region else "미추출"
        note = (
            "제목의 [지역] 표기 기반 추정으로 재계산됨 (2026-09-04 보정)"
            if new_region
            else "제목에 지역 표기가 없어 확인 불가 — 기관명을 지역으로 "
            "대체하던 기존 방식을 폐기함 (2026-09-04 보정)"
        )
        conn.execute(
            """INSERT INTO program_fields
               (program_id, field_name, field_value, confirmation_status, source_document_id, section_text, collected_at)
               VALUES (?, '지역', ?, ?, ?, ?, ?)""",
            (p["id"], new_region, confirmation, doc["id"] if doc else None, note, now),
        )
        conn.execute("UPDATE programs SET region_display = ? WHERE id = ?", (new_region, p["id"]))
        changed.append((p["id"], p["title"][:30], old_value, new_region))
    return changed


def fix_organizations(conn):
    removed = []
    for name in NON_ORG_NAME_VALUES:
        org = conn.execute("SELECT id FROM organizations WHERE name = ?", (name,)).fetchone()
        if not org:
            continue
        org_id = org["id"]
        role_count = conn.execute(
            "SELECT COUNT(*) c FROM program_organization_roles WHERE org_id = ?", (org_id,)
        ).fetchone()["c"]
        conn.execute(
            "DELETE FROM organization_relationships WHERE from_org_id = ? OR to_org_id = ?",
            (org_id, org_id),
        )
        conn.execute("DELETE FROM program_organization_roles WHERE org_id = ?", (org_id,))
        conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
        removed.append((name, org_id, role_count))
    return removed


def main() -> int:
    conn = get_connection()

    print("=== P0-1: 지역 보정 ===")
    region_changes = fix_regions(conn)
    for pid, title, old, new in region_changes:
        print(f"  program {pid} [{title}]: '{old}' -> {new!r}")
    print(f"보정된 지역 값: {len(region_changes)}건")

    print()
    print("=== P0-2: 기관명 오분류 보정 ===")
    removed_orgs = fix_organizations(conn)
    for name, org_id, role_count in removed_orgs:
        print(f"  제거됨: organizations.id={org_id} name='{name}' (연결된 공고-기관 역할 {role_count}건도 함께 제거)")
    print(f"제거된 오분류 기관: {len(removed_orgs)}건")

    conn.commit()

    total_programs = conn.execute("SELECT COUNT(*) c FROM programs").fetchone()["c"]
    total_orgs = conn.execute("SELECT COUNT(*) c FROM organizations").fetchone()["c"]
    print()
    print(f"[결과] programs: {total_programs}건 (변화 없어야 정상) / organizations: {total_orgs}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
