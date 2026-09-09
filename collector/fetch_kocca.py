"""한국콘텐츠진흥원 지원사업 목록을 원본으로 보존하는 수집기."""

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.kocca_adapter import KoccaAdapter  # noqa: E402
from adapters.base import ReadinessStatus  # noqa: E402
from common.env import get_env_value  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PAGES_DIR = PROJECT_ROOT / "collector" / "raw" / "kocca" / "pages"
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "kocca" / "items"


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="현재 API 목록 전체 페이지를 수집합니다.")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.4)
    args = parser.parse_args()
    if min(args.page_size, args.max_pages) < 1 or args.delay < 0:
        print("[결과] 실패 — page-size/max-pages는 1 이상이고 delay는 0 이상이어야 합니다.")
        return 1

    adapter = KoccaAdapter()
    if adapter.check_readiness() != ReadinessStatus.READY:
        print("[결과] 실패 — KOCCA_API_KEY가 준비되지 않았습니다.")
        return 1
    page_size = args.page_size if args.full else 5
    first = adapter.fetch_list_response(page=1, page_size=page_size)
    if not first:
        print("[결과] 실패 — API 응답이 없습니다.")
        return 1
    info = first.get("INFO", {})
    total = int(info.get("listCount") or 0)
    planned = min(math.ceil(total / page_size) if total else args.max_pages, args.max_pages)
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_items = []
    for page in range(1, planned + 1):
        response = first if page == 1 else adapter.fetch_list_response(page=page, page_size=page_size)
        if not response:
            return 1
        write_json(RAW_PAGES_DIR / f"{collected_at.replace(':', '').replace('-', '').replace(' ', '_')}_page{page}.json", response)
        items = response.get("INFO", {}).get("list", [])
        print(f"[정보] page {page}: {len(items)}건 수신")
        all_items.extend(items)
        if not items or (total and len(all_items) >= total):
            break
        if page < planned and args.delay:
            time.sleep(args.delay)

    seen = set()
    unique = []
    for item in all_items:
        item_id = str(item.get("intcNoSeq") or "UNKNOWN")
        if item_id in seen:
            continue
        seen.add(item_id)
        unique.append(item)
        path = RAW_ITEMS_DIR / item_id / f"{collected_at.replace(':', '').replace('-', '').replace(' ', '_')}.json"
        write_json(path, item)
    print(f"[결과] KOCCA 고유 공고 {len(unique)}건 원본 저장 완료")
    print(f"[정보] API 키 상태: 길이 {len(get_env_value('KOCCA_API_KEY'))}자(값 미출력)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
