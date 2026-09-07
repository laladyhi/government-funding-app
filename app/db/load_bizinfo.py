"""
collector/mapped/bizinfo_mapped.json (+ collector/raw 원본)을 읽어
SQLite에 적재한다.

원칙:
  - collector/ 아래 원본 파일은 읽기 전용으로만 사용한다 (쓰거나 지우지 않음).
  - source_item_id(pblancId) 기준으로 이미 있는 지원사업은 다시 만들지 않는다
    (UNIQUE(source, source_item_id) 제약 + 이 스크립트의 조회 로직).
  - 값이 불확실하면(추정/미추출) 있는 그대로 저장하고 확정된 값처럼 꾸미지 않는다.
  - 재실행해도 안전하다 (이미 적재된 원본/필드는 건너뜀).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MAPPED_PATH = PROJECT_ROOT / "collector" / "mapped" / "bizinfo_mapped.json"
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "bizinfo" / "items"
RAW_PAGES_DIR = PROJECT_ROOT / "collector" / "raw" / "bizinfo" / "pages"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate import get_connection  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from fetch_and_store import compute_file_hash  # noqa: E402  (해시 계산의 단일 기준)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 기업마당 API가 실제 기관명 대신 돌려주는 일반 유형 표현들.
# 이런 값은 특정 기관을 가리키지 않으므로 organizations에 저장하지 않는다
# (데이터 품질 점검 2026-09-04, 문제 2·3). 새로운 값을 발견하면 이 목록에만
# 추가하면 되고, 나머지 로직은 바꿀 필요 없다.
NON_ORG_NAME_VALUES = {"기초자치단체", "직접수행"}


def normalize_confirmation(raw_label: str):
    """
    수집 단계(collector)에서 붙인 서술적인 라벨을
    DB의 고정된 확인상태 값 5개 중 하나로 정규화하고,
    나머지 설명은 section_text로 분리해서 보존한다.
    """
    if raw_label is None:
        return "미추출", None
    if raw_label.startswith("확인된 사실"):
        return "확인된 사실", None
    if raw_label.startswith("AI 분석"):
        note = raw_label[len("AI 분석") :].strip(" ()")
        return "AI 분석", (note or None)
    if raw_label.startswith("추정"):
        note = raw_label[len("추정") :].strip(" ()")
        return "추정", (note or None)
    if raw_label.startswith("미추출"):
        return "미추출", raw_label
    if raw_label.startswith("해당없음"):
        return "해당없음", None
    return "미추출", raw_label


def get_or_create_organization(conn, name: str):
    """
    name이 실제 기관명이 아니라 "기초자치단체"·"직접수행" 같은 일반
    유형 표현이면 organization을 만들지 않고 None을 반환한다 — 화면에는
    "기관명 미확인"으로 표시된다. 원본 API 값(program_fields의
    주관기관/소관기관)은 이 함수와 무관하게 그대로 보존된다.
    """
    if not name or name in NON_ORG_NAME_VALUES:
        return None
    row = conn.execute("SELECT id FROM organizations WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO organizations (name, data_collection_method) VALUES (?, ?)",
        (name, "API(기업마당)"),
    )
    return cur.lastrowid


def get_relationship_type_id(conn, name: str):
    row = conn.execute("SELECT id FROM relationship_types WHERE name = ?", (name,)).fetchone()
    if not row:
        raise ValueError(f"알 수 없는 relationship_type: {name} (스키마에 먼저 추가 필요)")
    return row[0]


def get_scheme_id(conn, axis_name: str):
    row = conn.execute(
        """
        SELECT cs.id FROM classification_schemes cs
        JOIN classification_axes ca ON ca.id = cs.axis_id
        WHERE ca.name = ?
        """,
        (axis_name,),
    ).fetchone()
    if not row:
        raise ValueError(f"알 수 없는 분류축: {axis_name}")
    return row[0]


def get_or_create_node(conn, scheme_id: int, display_name: str, parent_node_id=None):
    if not display_name:
        return None
    row = conn.execute(
        "SELECT id FROM classification_nodes WHERE scheme_id = ? AND display_name = ?",
        (scheme_id, display_name),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO classification_nodes (scheme_id, parent_node_id, display_name) VALUES (?, ?, ?)",
        (scheme_id, parent_node_id, display_name),
    )
    return cur.lastrowid


def load_latest_raw_item_file(pblanc_id: str):
    item_dir = RAW_ITEMS_DIR / pblanc_id
    if not item_dir.exists():
        return None
    files = sorted(item_dir.glob("*.json"))
    return files[-1] if files else None


def insert_raw_response_if_new(conn, source, source_item_id, response_type, path: Path, collected_at):
    """
    path가 가리키는 실제 파일에서 내용과 해시를 함께 읽어온다 — 해시는
    항상 compute_file_hash(path)로만 계산한다 (docs/raw-data-hash-policy.md).
    """
    raw_json_text = path.read_text(encoding="utf-8")
    content_hash = compute_file_hash(path)
    existing = conn.execute(
        """
        SELECT id FROM raw_api_responses
        WHERE source = ? AND response_type = ? AND content_hash = ?
          AND (source_item_id IS ? OR source_item_id = ?)
        """,
        (source, response_type, content_hash, source_item_id, source_item_id),
    ).fetchone()
    if existing:
        return existing[0], False
    cur = conn.execute(
        """
        INSERT INTO raw_api_responses (source, source_item_id, response_type, raw_json, collected_at, content_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source, source_item_id, response_type, raw_json_text, collected_at, content_hash),
    )
    return cur.lastrowid, True


def load_program(conn, mapped_program: dict) -> str:
    source = mapped_program["source"]
    source_item_id = mapped_program["source_item_id"]
    fields = mapped_program["fields"]
    src_doc = mapped_program["source_document"]
    attachments = mapped_program.get("attachments", {})

    raw_item_path = load_latest_raw_item_file(source_item_id)
    # 해시는 mapped JSON에 적힌 값을 신뢰하지 않고, 항상 실제 raw 파일에서
    # 직접 다시 계산한다 — 이게 유일한 기준이다 (docs/raw-data-hash-policy.md).
    new_hash = compute_file_hash(raw_item_path) if raw_item_path else src_doc["원본_해시"]
    collected_at = src_doc["수집일"]

    existing = conn.execute(
        "SELECT id, latest_raw_hash FROM programs WHERE source = ? AND source_item_id = ?",
        (source, source_item_id),
    ).fetchone()

    if existing and existing[1] == new_hash:
        return "unchanged"  # 이미 같은 내용으로 적재됨 — 건너뜀

    title = fields["사업명"]["value"]
    status_computed = fields["공고상태"]["value"]
    period_display = fields["신청기간_원문"]["value"]
    target_display = fields["대상기업"]["value"]
    region_display = fields["지역"]["value"]
    amount_display = fields["지원금액"]["value"]  # Phase1은 대부분 None(미추출)

    if existing:
        program_id = existing[0]
        conn.execute(
            """
            UPDATE programs SET
              title = ?, status_computed = ?, application_period_display = ?,
              amount_display = ?, target_company_display = ?, region_display = ?,
              last_updated_at = ?, latest_raw_hash = ?
            WHERE id = ?
            """,
            (title, status_computed, period_display, amount_display, target_display,
             region_display, collected_at, new_hash, program_id),
        )
        outcome = "updated"
    else:
        cur = conn.execute(
            """
            INSERT INTO programs (
              source, source_item_id, title, status_computed, application_period_display,
              amount_display, target_company_display, region_display,
              first_collected_at, last_updated_at, latest_raw_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source, source_item_id, title, status_computed, period_display, amount_display,
             target_display, region_display, collected_at, collected_at, new_hash),
        )
        program_id = cur.lastrowid
        outcome = "inserted"

    # 기관 연결: 주관(수행)기관, 소관기관
    exec_org_name = fields["주관기관"]["value"]
    jrsd_org_name = fields["소관기관"]["value"]
    exec_org_id = get_or_create_organization(conn, exec_org_name)
    jrsd_org_id = get_or_create_organization(conn, jrsd_org_name)

    if exec_org_id:
        role_id = get_relationship_type_id(conn, "주관")
        conn.execute(
            "INSERT OR IGNORE INTO program_organization_roles (program_id, org_id, role_type_id) VALUES (?, ?, ?)",
            (program_id, exec_org_id, role_id),
        )
    if jrsd_org_id:
        role_id = get_relationship_type_id(conn, "소관")
        conn.execute(
            "INSERT OR IGNORE INTO program_organization_roles (program_id, org_id, role_type_id) VALUES (?, ?, ?)",
            (program_id, jrsd_org_id, role_id),
        )

    # 원문 웹페이지 출처 문서
    webpage_doc_id = conn.execute(
        """
        INSERT INTO source_documents (program_id, document_type, source_org, url, collected_at, content_hash)
        VALUES (?, '웹페이지', '기업마당', ?, ?, ?)
        """,
        (program_id, src_doc["원문_상세_URL"], collected_at, new_hash),
    ).lastrowid

    # 첨부파일 출처 문서
    if attachments.get("parsed"):
        for f in attachments["files"]:
            conn.execute(
                """
                INSERT INTO source_documents (program_id, document_type, source_org, url, file_name, collected_at)
                VALUES (?, '첨부파일', '기업마당', ?, ?, ?)
                """,
                (program_id, f["url"], f["name"], collected_at),
            )

    # 기존 필드 스냅샷은 남겨두고(이력), 새 스냅샷을 추가한다
    for field_name, field_info in fields.items():
        confirmation, note = normalize_confirmation(field_info["confirmation"])
        conn.execute(
            """
            INSERT INTO program_fields (
              program_id, field_name, field_value, confirmation_status,
              source_document_id, section_text, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (program_id, field_name, field_info["value"], confirmation,
             webpage_doc_id, note, collected_at),
        )

    # 지원분야 분류 연결 (대분류 -> 중분류, 트리)
    scheme_id = get_scheme_id(conn, "지원분야분류")
    lclas = fields["지원분야_대분류"]["value"]
    mlsfc = fields["지원분야_중분류"]["value"]
    lclas_node_id = get_or_create_node(conn, scheme_id, lclas) if lclas else None
    if lclas_node_id and mlsfc:
        mlsfc_node_id = get_or_create_node(conn, scheme_id, mlsfc, parent_node_id=lclas_node_id)
        conn.execute(
            "INSERT OR IGNORE INTO program_classifications (program_id, node_id, link_basis) VALUES (?, ?, '원문명시')",
            (program_id, mlsfc_node_id),
        )
    if lclas_node_id:
        conn.execute(
            "INSERT OR IGNORE INTO program_classifications (program_id, node_id, link_basis) VALUES (?, ?, '원문명시')",
            (program_id, lclas_node_id),
        )

    # 원본 API 응답 보존 (item 단위) — 위에서 이미 구한 raw_item_path 재사용
    if raw_item_path:
        insert_raw_response_if_new(conn, source, source_item_id, "item", raw_item_path, collected_at)

    return outcome


def load_page_level_raw(conn):
    if not RAW_PAGES_DIR.exists():
        return 0
    count = 0
    for path in sorted(RAW_PAGES_DIR.glob("*.json")):
        collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _, is_new = insert_raw_response_if_new(conn, "bizinfo", None, "page", path, collected_at)
        if is_new:
            count += 1
    return count


def main() -> int:
    if not MAPPED_PATH.exists():
        print(f"[결과] 실패 — {MAPPED_PATH} 가 없습니다. 먼저 collector/fetch_and_store.py를 실행하세요.")
        return 1

    mapped_programs = json.loads(MAPPED_PATH.read_text(encoding="utf-8"))
    conn = get_connection()

    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for mp in mapped_programs:
        outcome = load_program(conn, mp)
        counts[outcome] += 1
    conn.commit()

    new_pages = load_page_level_raw(conn)
    conn.commit()

    print(f"[결과] 신규 {counts['inserted']}건, 갱신 {counts['updated']}건, 변경없음(건너뜀) {counts['unchanged']}건")
    print(f"[정보] 원본 페이지 응답 {new_pages}건 신규 보존")

    total_programs = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    total_fields = conn.execute("SELECT COUNT(*) FROM program_fields").fetchone()[0]
    total_orgs = conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0]
    print(f"[정보] DB 현황 — programs: {total_programs}, program_fields: {total_fields}, organizations: {total_orgs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
