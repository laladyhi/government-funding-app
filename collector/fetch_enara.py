"""e나라도움 국고보조금 공모사업 원본 수집기."""

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import ReadinessStatus  # noqa: E402
from adapters.enara_adapter import EnaraAdapter, extract_items, extract_total_count  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PAGES_DIR = PROJECT_ROOT / "collector" / "raw" / "enara" / "pages"
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "enara" / "items"


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    if value is None:
        return ""
    text = str(value).strip()
    return text.replace("<![CDATA[", "").replace("]]>", "").strip()


def safe_item_id(item: dict) -> str:
    """API ID를 Windows 폴더명으로 사용할 수 있는 안전한 값으로 만든다."""
    item_id = _text(item, "DTLBZ_ID") or _text(item, "DTLBZ_DDTLBZ_ID")
    safe = "".join("_" if char in '<>:"/\\|?*' or ord(char) < 32 else char for char in item_id)
    safe = safe.strip(" .")
    if safe:
        return safe
    digest = hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return f"UNKNOWN_{digest[:16]}"


def is_actionable_announcement(item: dict) -> bool:
    """공모·지원 공고로 화면에 보여줄 최소 조건.

    이 API에는 공고정보와 단순 사업구조정보가 함께 들어 있다.
    공고명과 공고/접수 기간 중 하나가 없는 구조정보는 기본 저장 대상에서
    제외한다. 원본 페이지는 별도로 보존해 나중에 기준을 바꿀 수 있다.
    """
    title = _text(item, "PBLANC_NM")
    has_period = any(
        _text(item, key)
        for key in ("RCEPT_BEGIN_DE", "RCEPT_END_DE", "PBLANC_BEGIN_DE", "PBLANC_END_DE")
    )
    return bool(title and has_period)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="전체 페이지를 수집합니다.")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--year", type=int, default=datetime.now().year, help="조회할 사업연도")
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="공고 필터 없이 모든 원본 항목을 저장합니다(권장하지 않음).",
    )
    args = parser.parse_args()
    if min(args.page_size, args.max_pages) < 1 or args.page_size > 1000 or args.delay < 0:
        print("[결과] 실패 — page-size/max-pages는 1 이상이고 delay는 0 이상이어야 합니다.")
        return 1
    adapter = EnaraAdapter()
    if adapter.check_readiness() != ReadinessStatus.READY:
        print("[결과] 실패 — ENARA_API_KEY가 준비되지 않았습니다.")
        return 1
    page_size = args.page_size
    first = adapter.fetch_list_response(page=1, page_size=page_size, business_year=args.year)
    if not first:
        print("[결과] 실패 — API 응답이 없습니다.")
        return 1
    total = extract_total_count(first)
    planned = min(math.ceil(total / page_size) if args.full and total else (args.max_pages if args.full else 1), args.max_pages)
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    selected_items = []
    total_seen = 0
    filtered_out = 0
    for page in range(1, planned + 1):
        response = first if page == 1 else adapter.fetch_list_response(
            page=page,
            page_size=page_size,
            business_year=args.year,
        )
        if not response:
            return 1
        stamp = collected_at.replace(":", "").replace("-", "").replace(" ", "_")
        write_json(RAW_PAGES_DIR / f"{stamp}_page{page}.json", response)
        items = extract_items(response)
        print(f"[정보] page {page}: {len(items)}건 수신")
        total_seen += len(items)
        for item in items:
            if args.include_all or is_actionable_announcement(item):
                selected_items.append(item)
            else:
                filtered_out += 1
        if not items or (total and total_seen >= total):
            break
        if page < planned and args.delay:
            time.sleep(args.delay)
    seen = set()
    unique = []
    for item in selected_items:
        item_id = safe_item_id(item)
        if item_id in seen:
            continue
        seen.add(item_id)
        unique.append(item)
        write_json(RAW_ITEMS_DIR / item_id / f"{collected_at.replace(':', '').replace('-', '').replace(' ', '_')}.json", item)
    print(f"[결과] 전체 수신 {total_seen}건 / 공고로 선별 {len(unique)}건 / 구조정보 제외 {filtered_out}건")
    print("[결과] e나라도움 선별 원본 저장 완료")
    print("[정보] 운영 DB에는 아직 저장하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
