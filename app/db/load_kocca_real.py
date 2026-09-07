"""
KOCCA(한국콘텐츠진흥원) — 실제 API 응답(collector/sample_kocca_response.json,
2026-09-07 실 호출로 확보된 4건)을 운영 DB 스키마 기준으로 미리보기/적재하는
스크립트.

기본은 항상 dry-run(미리보기)이다 — 아무것도 저장하지 않는다. 실제로 운영
DB(app/data/govfunding.sqlite3)에 적재하려면 반드시 --commit 옵션을 명시해야
한다. 이 스크립트는 네트워크를 호출하지 않는다 — collector/test_kocca_api.py가
이미 저장해 둔 테스트용 원본만 읽는다.

수행 내용:
  1. collector/sample_kocca_response.json(테스트용 위치)에 있는 실 응답을
     collector/raw/kocca/items/<intcNoSeq>/<수집시각>.json 로 정식 원본
     보존 위치에 옮겨 저장한다(bizinfo/public_benefits와 동일한 바이트
     저장 방식). 이미 같은 내용으로 저장된 적이 있으면 새로 만들지 않는다.
  2. 저장된 파일 "바이트 자체"로 SHA-256 해시를 계산한다
     (docs/raw-data-hash-policy.md 기준).
  3. KoccaAdapter.to_standard_program()으로 표준 구조 변환
     (실제 필드명 resultMgs/cate/regDt/title/intcNoSeq/link/startDt/endDt/
     content 사용, YYYYMMDD 날짜를 정상 변환).
  4. 운영 DB(읽기 전용 조회)를 기준으로 "적재하면 무엇이 일어날지" 미리
     계산한다 (신규/갱신/변경없음) — dry-run에서는 실제로 쓰지 않는다.
  5. 기존 기업마당·K-Startup(운영 DB)과 정부24(collector/raw/public_benefits/
     — 아직 운영 DB에는 없으므로 저장된 원본 파일 기준)를 대상으로 제목·
     사업번호(source_item_id)·게시글 링크 3가지 기준으로 중복 후보를 확인한다.

사용법:
  python app/db/load_kocca_real.py            # 미리보기만 (기본)
  python app/db/load_kocca_real.py --commit    # 실제 운영 DB에 적재
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_PATH = PROJECT_ROOT / "collector" / "sample_kocca_response.json"
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "kocca" / "items"
PUBLIC_BENEFITS_RAW_DIR = PROJECT_ROOT / "collector" / "raw" / "public_benefits" / "items"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from load_standard_program import load_standard_program  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.kocca_adapter import KoccaAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def compute_file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_bytes(path: Path, data) -> Path:
    content_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(content_bytes)
    return path


def archive_raw_items() -> list:
    """테스트용 위치의 실 응답을 정식 raw 보존 위치로 옮겨 저장한다."""
    if not SAMPLE_PATH.exists():
        return []
    data = json.loads(SAMPLE_PATH.read_bytes().decode("utf-8"))
    info = data.get("INFO", {})
    if info.get("resultCode") != "INFO-000":
        return []

    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts = collected_at.replace(":", "").replace("-", "").replace(" ", "_")

    saved = []
    for item in info.get("list", []):
        service_id = item.get("intcNoSeq", "UNKNOWN")
        item_dir = RAW_ITEMS_DIR / service_id
        item_dir.mkdir(parents=True, exist_ok=True)
        path = item_dir / f"{ts}.json"
        _write_json_bytes(path, item)
        saved.append((path, item))
    return saved


def load_latest_raw_dir(base_dir: Path) -> list:
    """서비스ID 폴더마다 가장 최근(파일명 기준) 스냅샷 1건씩 읽는다."""
    results = []
    if not base_dir.exists():
        return results
    for service_dir in sorted(base_dir.iterdir()):
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
    backup_path = BACKUP_DIR / f"govfunding_before_kocca_load_{ts}.sqlite3"
    shutil.copyfile(DB_PATH, backup_path)
    return backup_path


def preview_outcome(conn, program) -> str:
    existing = conn.execute(
        "SELECT id, latest_raw_hash FROM programs WHERE source = ? AND source_item_id = ?",
        (program.source, program.source_program_id),
    ).fetchone()
    if existing and existing["latest_raw_hash"] == program.content_hash and program.content_hash:
        return "unchanged"
    if existing:
        return "updated"
    return "inserted"


def check_duplicates(conn, program, pb_entries):
    """제목/사업번호(source_item_id)/게시글 링크 3가지 기준으로 중복 후보를 찾는다."""
    matches = []

    # 1) 기업마당·K-Startup (운영 DB)
    core_title = program.title.replace("[가상데이터] ", "")[:10]
    rows = conn.execute(
        """
        SELECT title, source, source_item_id
        FROM programs
        WHERE source IN ('bizinfo', 'kstartup')
          AND (title LIKE ? OR source_item_id = ?)
        """,
        (f"%{core_title}%", program.source_program_id),
    ).fetchall()
    for r in rows:
        matches.append(f"{r['source']}:{r['source_item_id']} ({r['title'][:20]}...)")

    # source_url 링크 기준 (운영 DB의 웹페이지 문서 URL과 비교)
    if program.source_url:
        url_rows = conn.execute(
            """
            SELECT sd.url, p.source, p.source_item_id
            FROM source_documents sd JOIN programs p ON p.id = sd.program_id
            WHERE sd.document_type = '웹페이지' AND sd.url = ?
            """,
            (program.source_url,),
        ).fetchall()
        for r in url_rows:
            matches.append(f"{r['source']}:{r['source_item_id']} (동일 링크)")

    # 2) 정부24(public_benefits) — 아직 운영 DB에 없으므로 raw 파일 기준
    for _, pb_raw in pb_entries:
        pb_title = pb_raw.get("서비스명", "")
        pb_id = pb_raw.get("서비스ID", "")
        pb_url = pb_raw.get("상세조회URL", "")
        if (
            (pb_title and core_title and core_title in pb_title)
            or (pb_id and pb_id == program.source_program_id)
            or (pb_url and program.source_url and pb_url == program.source_url)
        ):
            matches.append(f"public_benefits:{pb_id} ({pb_title[:20]}...)")

    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true",
        help="실제로 운영 DB에 적재한다. 지정하지 않으면 미리보기만 하고 아무것도 저장하지 않는다.",
    )
    args = parser.parse_args()

    archived = archive_raw_items()
    raw_entries = load_latest_raw_dir(RAW_ITEMS_DIR)
    if not raw_entries:
        print(f"[결과] 실패 — 읽을 원본 파일이 없습니다: {RAW_ITEMS_DIR}")
        print(f"({SAMPLE_PATH}이 있는지, INFO.resultCode가 INFO-000인지 확인하세요.)")
        return 1

    print(f"[정보] 원본을 정식 보존 위치로 저장했습니다: {RAW_ITEMS_DIR} ({len(archived)}건)")

    adapter = KoccaAdapter()
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    converted = []
    for path, raw_item in raw_entries:
        program = adapter.to_standard_program(raw_item)
        program.content_hash = compute_file_hash(path)
        program.collected_at = collected_at
        converted.append((program, raw_item, path))

    conn = get_connection()
    pb_entries = load_latest_raw_dir(PUBLIC_BENEFITS_RAW_DIR)

    print(f"\n=== 변환 결과 미리보기 ({len(converted)}건) ===\n")
    table_rows = []
    for program, raw_item, path in converted:
        outcome = preview_outcome(conn, program)
        dup_matches = check_duplicates(conn, program, pb_entries)
        dup_display = "; ".join(dup_matches) if dup_matches else "중복 후보 없음"

        table_rows.append({
            "title": program.title,
            "source_item_id": program.source_program_id,
            "category": raw_item.get("cate"),
            "start": program.application_start,
            "end": program.application_end,
            "link": program.source_url,
            "dup": dup_display,
            "db_change": "없음(dry-run)",
        })

        print(f"  - source_program_id={program.source_program_id}  title={program.title!r}")
        print(f"    분류(cate)={raw_item.get('cate')!r}  접수기간={program.application_start}~{program.application_end}")
        print(f"    link={program.source_url}")
        print(f"    content_hash={program.content_hash}")
        print(f"    원본 파일: {path}")
        print(f"    [미리보기] 적재하면: {outcome}")
        print(f"    중복 확인: {dup_display}")
        print()

    print("\n=== 표 (요청 형식) ===")
    print(f"{'제목':<45} | {'사업번호':<14} | {'분류':<8} | {'접수시작':<10} | {'접수마감':<10} | {'중복여부':<14} | 운영DB변경")
    for r in table_rows:
        title_disp = (r["title"][:42] + "...") if len(r["title"]) > 42 else r["title"]
        print(f"{title_disp:<45} | {r['source_item_id']:<14} | {str(r['category']):<8} | {str(r['start']):<10} | {str(r['end']):<10} | {r['dup'][:14]:<14} | {r['db_change']}")

    if not args.commit:
        print(f"\n[DRY-RUN] 실제로 저장하지 않았습니다 ({len(converted)}건 미리보기만).")
        print("[DRY-RUN] 운영 DB에 적재하려면 --commit 옵션을 붙여 다시 실행하세요 (사용자 별도 승인 필요).")
        prod_total = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
        prod_kocca = conn.execute("SELECT COUNT(*) FROM programs WHERE source='kocca'").fetchone()[0]
        print(f"[확인] 운영 DB programs 총 건수(변경 없음): {prod_total} (kocca: {prod_kocca})")
        return 0

    # --commit 모드
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
