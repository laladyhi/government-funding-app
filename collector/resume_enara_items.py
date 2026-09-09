"""이미 저장된 e나라도움 페이지 원본에서 선별 항목 파일만 재생성한다."""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.enara_adapter import extract_items  # noqa: E402
from fetch_enara import is_actionable_announcement, safe_item_id, write_json  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = PROJECT_ROOT / "collector" / "raw" / "enara" / "pages"
ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "enara" / "items"


def main() -> int:
    page_paths = sorted(PAGES_DIR.glob("*.json"))
    if not page_paths:
        print("[결과] 저장된 페이지 원본이 없습니다.")
        return 1
    selected = {}
    total_seen = 0
    excluded = 0
    for path in page_paths:
        try:
            response = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"[경고] 원본 파일을 읽지 못해 건너뜀: {path.name} ({exc})")
            continue
        items = extract_items(response)
        total_seen += len(items)
        for item in items:
            if not is_actionable_announcement(item):
                excluded += 1
                continue
            selected[safe_item_id(item)] = item
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stamp = collected_at.replace(":", "").replace("-", "").replace(" ", "_")
    for item_id, item in selected.items():
        write_json(ITEMS_DIR / item_id / f"{stamp}.json", item)
    print(f"[결과] 페이지 원본 {len(page_paths)}개 / 전체 항목 {total_seen}건")
    print(f"[결과] 공고 선별 {len(selected)}건 / 구조정보 제외 {excluded}건")
    print("[정보] 운영 DB에는 아직 저장하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
