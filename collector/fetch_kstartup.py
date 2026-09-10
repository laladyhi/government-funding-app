"""K-Startup 지원사업 공고 전체 수집기.

기본 실행은 5건 1페이지로 제한한다. ``--plan``은 첫 응답의 전체 건수와
예정 페이지 수만 확인하고 파일을 만들지 않는다. ``--full``을 명시했을
때만 전체 페이지를 원본 파일로 보존한다. API 키와 원문 응답의 민감한
값은 출력하지 않는다.
"""

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
RAW_PAGES_DIR = PROJECT_ROOT / "collector" / "raw" / "kstartup" / "pages"
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "kstartup" / "items"
DEFAULT_PAGE_SIZE = 5
DEFAULT_FULL_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 500

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_env() -> dict:
    values = {}
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def mask(value: str) -> str:
    return f"(길이 {len(value)}자, ****로 마스킹됨)" if value else "(비어있음)"


def request_page(api_key: str, page: int, page_size: int, retries: int = 3) -> dict:
    # 공공데이터포털 Encoding 키는 이미 URL 인코딩되어 있으므로 그대로 붙인다.
    query = urllib.parse.urlencode({"page": page, "perPage": page_size, "returnType": "json"})
    url = f"{API_URL}?ServiceKey={api_key}&{query}"
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("API 응답이 JSON 객체가 아닙니다.")
            if data.get("resultCode") not in (None, "00", "0", 0):
                raise ValueError(f"API 오류: {data.get('resultCode')} {data.get('resultMsg')}")
            return data
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                print(f"[정보] page {page} 요청 실패({attempt}/{retries}), 재시도합니다: {exc}")
                time.sleep(2 * attempt)
    raise last_error


def extract_items(payload: dict) -> list:
    for key in ("data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("data"), list):
        return response["data"]
    return []


def extract_total_count(payload: dict) -> int | None:
    values = [payload.get(k) for k in ("totalCount", "matchCount", "totCnt")]
    response = payload.get("response")
    if isinstance(response, dict):
        values.extend(response.get(k) for k in ("totalCount", "matchCount", "totCnt"))
    for value in values:
        try:
            if value is not None:
                return int(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
    return None


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def save_page(page: int, payload: dict, collected_at: str) -> Path:
    stamp = collected_at.replace(":", "").replace("-", "").replace(" ", "_")
    path = RAW_PAGES_DIR / f"{stamp}_page{page}.json"
    write_json(path, payload)
    return path


def save_item(item: dict, collected_at: str) -> Path:
    item_id = str(item.get("pbanc_sn") or "UNKNOWN")
    stamp = collected_at.replace(":", "").replace("-", "").replace(" ", "_")
    path = RAW_ITEMS_DIR / item_id / f"{stamp}.json"
    write_json(path, item)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="전체 페이지를 수집합니다.")
    parser.add_argument("--plan", action="store_true", help="전체 건수와 예정 페이지 수만 확인합니다.")
    parser.add_argument("--pages", type=int, default=1, help="--full이 아닐 때 호출할 페이지 수")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="기본 페이지당 건수")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="안전장치용 최대 페이지 수")
    parser.add_argument("--delay", type=float, default=0.4, help="페이지 사이 대기 시간(초)")
    args = parser.parse_args()
    if min(args.pages, args.page_size, args.max_pages) < 1 or args.delay < 0:
        print("[결과] 실패 — pages, page-size, max-pages는 1 이상이고 delay는 0 이상이어야 합니다.")
        return 1

    api_key = load_env().get("KSTARTUP_API_KEY", "")
    if not api_key:
        print("[결과] 실패 — .env에 KSTARTUP_API_KEY가 없습니다.")
        return 1
    page_size = DEFAULT_FULL_PAGE_SIZE if args.full else args.page_size
    print(f"[정보] KSTARTUP_API_KEY 확인됨 {mask(api_key)} — 값 자체는 출력하지 않습니다.")

    try:
        first_payload = request_page(api_key, 1, page_size)
    except (requests.RequestException, ValueError) as exc:
        print(f"[결과] 실패 — 첫 페이지 요청 오류: {str(exc).replace(api_key, '****')}")
        return 1

    total_count = extract_total_count(first_payload)
    if args.full and total_count is not None:
        planned_pages = min(math.ceil(total_count / page_size), args.max_pages)
    elif args.full:
        planned_pages = args.max_pages
    else:
        planned_pages = min(args.pages, args.max_pages)
    print(f"[계획] 전체 건수: {total_count if total_count is not None else '확인 불가'}건, 예정 페이지: {planned_pages}")

    if args.plan:
        print("[계획] 파일 저장·DB 변경 없이 종료했습니다.")
        return 0

    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_items = []
    for page in range(1, planned_pages + 1):
        try:
            payload = first_payload if page == 1 else request_page(api_key, page, page_size)
        except (requests.RequestException, ValueError) as exc:
            print(f"[결과] 실패 — page {page} 요청 오류: {str(exc).replace(api_key, '****')}")
            return 1
        save_page(page, payload, collected_at)
        items = extract_items(payload)
        print(f"[정보] page {page}: {len(items)}건 수신")
        all_items.extend(items)
        if not items or (total_count is not None and len(all_items) >= total_count):
            break
        if page < planned_pages and args.delay:
            time.sleep(args.delay)

    seen = set()
    unique_items = []
    for item in all_items:
        item_id = str(item.get("pbanc_sn") or "UNKNOWN")
        if item_id in seen:
            continue
        seen.add(item_id)
        unique_items.append(item)
    saved = []
    for item in unique_items:
        path = save_item(item, collected_at)
        saved.append((item, path, hashlib.sha256(path.read_bytes()).hexdigest()))
    print(f"[결과] 고유 공고 {len(unique_items)}건 원본 저장 완료 (중복 {len(all_items) - len(unique_items)}건 제거)")
    print("[정보] 운영 DB에는 저장하지 않았습니다. DB 적재는 별도 dry-run/승인 단계입니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
