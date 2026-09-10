"""NTIS 국가R&D 과제검색 결과를 XML 원문과 항목별 JSON으로 저장한다."""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import ReadinessStatus  # noqa: E402
from adapters.ntis_adapter import NtisAdapter  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "collector" / "raw" / "ntis"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword", required=True, help="NTIS SRWR 검색어")
    parser.add_argument("--search-field", default="BI", help="BI/TI/AU/OG/PB/KW/AB")
    parser.add_argument("--display-count", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.display_count <= 100 or args.max_pages < 1:
        print("[결과] 실패 — display-count는 1~100, max-pages는 1 이상이어야 합니다.")
        return 1
    adapter = NtisAdapter()
    if adapter.check_readiness() != ReadinessStatus.READY:
        print("[결과] 실패 — .env에 NTIS_API_KEY가 없거나 비어 있습니다.")
        return 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    page_dir = RAW_DIR / "pages"
    item_dir = RAW_DIR / "items"
    total = 0
    seen = set()
    for page in range(args.max_pages):
        start = 1 + page * args.display_count
        xml_text = adapter.fetch_response(args.keyword, start, args.display_count, args.search_field)
        if not xml_text:
            return 1
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / f"{stamp}_page{page + 1}.xml").write_text(xml_text, encoding="utf-8")
        items = adapter.parse_items(xml_text)
        for item in items:
            project_id = item.get("project_number") or hashlib.sha256(item["raw_xml"].encode()).hexdigest()[:16]
            if project_id in seen:
                continue
            seen.add(project_id)
            target = item_dir / str(project_id)
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{stamp}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        total += len(items)
        print(f"[정보] page {page + 1}: {len(items)}건 수신")
        if len(items) < args.display_count:
            break
    print(f"[결과] NTIS 원문 및 항목 저장 완료 — {total}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
