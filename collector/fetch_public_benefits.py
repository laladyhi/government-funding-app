"""
정부24 공공서비스(혜택) — 소상공인 대상 수집 스크립트.

collector/test_public_benefits_filtered.py(화면 확인용, 미저장)와 달리, 이
스크립트는 응답을 실제로 디스크에 원본 그대로 보존한다 — 다음 단계인
app/db/load_public_benefits_real.py가 이 파일들을 읽어 운영 DB 적재를
미리보기(dry-run)한다.

이 스크립트가 하는 일 (전부):
  1. 기본 실행은 5건만 호출하고, --full 실행은 응답의 전체 건수만큼 페이지를 호출.
  2. 서비스ID 기준으로 중복 제거 (같은 응답 안에 중복이 있을 경우 대비).
  3. 각 항목을 collector/raw/public_benefits/items/<서비스ID>/<수집시각>.json로
     원본 그대로 저장 (bizinfo와 동일한 바이트 저장 방식 — write_bytes,
     ensure_ascii=False, indent=2 — docs/raw-data-hash-policy.md 기준).
  4. 저장된 "파일 자체의 바이트"로 SHA-256 해시를 계산 (재직렬화 금지 원칙).

운영 DB에는 아무것도 쓰지 않는다. API 키 값은 절대 출력하지 않는다.

실행: python collector/fetch_public_benefits.py
"""

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
from adapters.public_benefits_adapter import PublicBenefitsAdapter  # noqa: E402
from common.env import get_env_value  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "public_benefits" / "items"

FILTER_KEYWORD = "소상공인"
MAX_RECORDS = 5
DEFAULT_FULL_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 500


def mask(value: str) -> str:
    if not value:
        return "(비어있음)"
    return f"(길이 {len(value)}자, ****로 마스킹됨)"


def compute_file_hash(path: Path) -> str:
    """docs/raw-data-hash-policy.md 기준 — 저장된 파일의 바이트 그대로 해시."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_bytes(path: Path, data) -> Path:
    content_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(content_bytes)
    return path


def save_raw_item(service_id: str, item: dict, collected_at: str) -> Path:
    item_dir = RAW_ITEMS_DIR / service_id
    item_dir.mkdir(parents=True, exist_ok=True)
    ts = collected_at.replace(":", "").replace("-", "").replace(" ", "_")
    path = item_dir / f"{ts}.json"
    return _write_json_bytes(path, item)


def extract_total_count(response: dict) -> int | None:
    for key in ("totalCount", "matchCount", "totCnt"):
        value = response.get(key)
        try:
            if value is not None:
                return int(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="소상공인 대상 전체 페이지를 수집합니다.")
    parser.add_argument("--plan", action="store_true", help="전체 건수와 예정 페이지 수만 확인하고 파일은 저장하지 않습니다.")
    parser.add_argument("--pages", type=int, default=1, help="--full이 아닐 때 호출할 페이지 수 (기본 1)")
    parser.add_argument("--page-size", type=int, default=MAX_RECORDS, help=f"기본 페이지당 건수 (기본 {MAX_RECORDS})")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help=f"안전장치용 최대 페이지 수 (기본 {DEFAULT_MAX_PAGES})")
    parser.add_argument("--delay", type=float, default=0.4, help="페이지 사이 대기 시간(초)")
    args = parser.parse_args()
    if args.pages < 1 or args.page_size < 1 or args.max_pages < 1 or args.delay < 0:
        print("[결과] 실패 — pages, page-size, max-pages는 1 이상이고 delay는 0 이상이어야 합니다.")
        return 1

    adapter = PublicBenefitsAdapter()
    readiness = adapter.check_readiness()

    api_key_len_info = mask(get_env_value(adapter.env_var_name))
    print(f"[정보] {adapter.env_var_name} 확인됨 {api_key_len_info} — 값 자체는 출력하지 않습니다.")
    print(f"[정보] 준비 상태: {readiness.value}")

    if readiness != ReadinessStatus.READY:
        print("[결과] 실패 — 키가 없어 실제 호출을 하지 않습니다.")
        return 1

    condition = {"cond[사용자구분::LIKE]": FILTER_KEYWORD}
    page_size = DEFAULT_FULL_PAGE_SIZE if args.full else args.page_size
    print(f"\n[정보] serviceList를 cond[사용자구분::LIKE]={FILTER_KEYWORD}, perPage={page_size}로 확인합니다...")
    first_response = adapter.fetch_list_response(page=1, page_size=page_size, cond=condition)
    if not first_response:
        print("[결과] 실패 — 응답을 받지 못했습니다.")
        return 1

    total_count = extract_total_count(first_response)
    if args.full and total_count is not None:
        planned_pages = min(math.ceil(total_count / page_size), args.max_pages)
    elif args.full:
        planned_pages = args.max_pages
    else:
        planned_pages = min(args.pages, args.max_pages)

    if args.plan:
        print(f"[계획] 전체 건수: {total_count if total_count is not None else '확인 불가'}건")
        print(f"[계획] 전체 수집 예정 페이지: {planned_pages}페이지")
        print("[계획] 파일 저장·DB 변경 없이 종료했습니다.")
        return 0

    items = []
    for page in range(1, planned_pages + 1):
        response = first_response if page == 1 else adapter.fetch_list_response(page=page, page_size=page_size, cond=condition)
        page_items = (response or {}).get("data", [])
        print(f"[정보] page {page}: {len(page_items)}건 수신")
        items.extend(page_items)
        if not page_items or (total_count is not None and len(items) >= total_count):
            break
        if page < planned_pages and args.delay:
            time.sleep(args.delay)

    if not items:
        print("[결과] 실패 또는 결과 0건 — collector/logs/public_benefits_errors.jsonl 확인 필요.")
        return 1

    print(f"[결과] 성공 — {len(items)}건 수신")

    # 서비스ID 기준 중복 제거 (같은 응답 안에서 중복이 있을 가능성 대비)
    seen_ids = set()
    unique_items = []
    duplicate_count = 0
    for item in items:
        service_id = item.get("서비스ID")
        if service_id in seen_ids:
            duplicate_count += 1
            continue
        seen_ids.add(service_id)
        unique_items.append(item)

    print(f"[정보] 서비스ID 기준 중복 제거: 수신 {len(items)}건 -> 고유 {len(unique_items)}건 (중복 {duplicate_count}건)")

    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved = []
    for item in unique_items:
        service_id = item.get("서비스ID", "UNKNOWN")
        path = save_raw_item(service_id, item, collected_at)
        file_hash = compute_file_hash(path)
        saved.append({"service_id": service_id, "title": item.get("서비스명"), "path": str(path), "hash": file_hash})

    print(f"\n[정보] 원본 저장 완료 ({len(saved)}건):")
    for entry in saved:
        print(f"  - {entry['service_id']}: {entry['title']!r}")
        print(f"    저장위치: {entry['path']}")
        print(f"    해시(SHA-256): {entry['hash']}")

    print("\n[정보] 운영 DB에는 아무것도 쓰지 않았습니다(이 스크립트는 DB를 열지 않습니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
