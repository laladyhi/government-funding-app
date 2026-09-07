"""
정부24 공공서비스(혜택) 데이터를 운영 DB에 적재하는 스크립트.

기본은 항상 dry-run(미리보기)이다 — 아무것도 저장하지 않는다.
실제로 운영 DB(app/data/govfunding.sqlite3)에 적재하려면 반드시
--commit 옵션을 명시해야 한다.

**주의**: 지금은 collector/fixtures/public_benefits_sample_response.json
(가상 값 fixture)만 있다. 실제 API 키로 검증된 진짜 응답이 아직 없으므로,
이 스크립트를 --commit으로 실행하는 것은 아직 권장하지 않는다 — 실제
호출 테스트(5건 이하) 이후, 그 결과로 만든 새 fixture를 가리키도록
FIXTURE_PATH를 바꾼 뒤에 사용해야 한다.

사용법:
  python app/db/load_public_benefits_sample.py            # 미리보기만 (기본)
  python app/db/load_public_benefits_sample.py --commit    # 실제 운영 DB에 적재
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_PATH = PROJECT_ROOT / "collector" / "fixtures" / "public_benefits_sample_response.json"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import get_connection  # noqa: E402
from load_standard_program import load_standard_program  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "collector"))
from adapters.public_benefits_adapter import PublicBenefitsAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def fixture_item_hash(item: dict) -> str:
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def backup_db() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"govfunding_before_public_benefits_load_{ts}.sqlite3"
    shutil.copyfile(DB_PATH, backup_path)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true",
        help="실제로 운영 DB에 적재한다. 지정하지 않으면 미리보기만 하고 아무것도 저장하지 않는다.",
    )
    args = parser.parse_args()

    if not FIXTURE_PATH.exists():
        print(f"[결과] 실패 — fixture 파일이 없습니다: {FIXTURE_PATH}")
        return 1

    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture.get("_is_real_data"):
        print("[정보] 이 fixture는 실제 데이터로 표시되어 있습니다.")
    else:
        print("[주의] 이 fixture는 가상 값입니다 (_is_real_data=false). "
              "--commit으로 운영 DB에 넣으면 가짜 공고가 실제 화면에 보이게 됩니다.")

    items = fixture["items"]
    adapter = PublicBenefitsAdapter()
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    converted = []
    for raw_item in items:
        program = adapter.to_standard_program(raw_item)
        program.content_hash = fixture_item_hash(raw_item)
        program.collected_at = collected_at
        converted.append((program, raw_item))

    if not args.commit:
        print(f"\n[DRY-RUN] 실제로 저장하지 않습니다 ({len(converted)}건 미리보기만). "
              f"운영 DB에 적재하려면 --commit 옵션을 붙여 다시 실행하세요.\n")
        for program, raw_item in converted:
            print(f"  - source_program_id={program.source_program_id}  title={program.title!r}")
            print(f"    organization={program.organization!r}  기간={program.application_start}~{program.application_end}")
        print(f"\n[DRY-RUN] 요약: {len(converted)}건이 저장 '시뮬레이션'만 되었습니다. DB는 변경되지 않았습니다.")
        return 0

    # --commit 모드
    if not fixture.get("_is_real_data"):
        print("[결과] 실패 — 가상 값 fixture는 --commit으로 적재할 수 없습니다. "
              "실제 API 응답으로 만든 fixture로 FIXTURE_PATH를 바꾼 뒤 다시 실행하세요.")
        return 1

    backup_path = backup_db()
    print(f"[정보] 적재 전 운영 DB 백업 완료: {backup_path}")

    conn = get_connection()
    before_count = conn.execute("SELECT COUNT(*) c FROM programs").fetchone()["c"]

    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0}
    for program, raw_item in converted:
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
