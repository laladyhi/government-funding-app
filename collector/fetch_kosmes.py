"""KOSMES 지원사업 공고 API 원문을 저장한다."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import ReadinessStatus  # noqa: E402
from adapters.kosmes_adapter import KosmesAdapter  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "collector" / "raw" / "kosmes"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--hashtag", default="")
    args = parser.parse_args()
    adapter = KosmesAdapter()
    if adapter.check_readiness() != ReadinessStatus.READY:
        print("[결과] 실패 - .env에 KOSMES_API_KEY가 없습니다.")
        return 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    page_dir = RAW_DIR / "pages"
    item_dir = RAW_DIR / "items"
    page_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    total = 0
    for page in range(1, args.max_pages + 1):
        response = adapter.fetch_response(page, args.page_size, hashtags=args.hashtag)
        if not response:
            print(f"[결과] 실패 - {adapter.last_error}")
            return 1
        (page_dir / f"{stamp}_page{page}.json").write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
        items = response.get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        for item in items:
            item_id = str(item.get("pblancId") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            target = item_dir / item_id
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{stamp}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        total += len(items)
        print(f"[정보] page {page}: {len(items)}건 수신")
        if len(items) < args.page_size:
            break
    print(f"[결과] KOSMES 원문 저장 완료 - {total}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
