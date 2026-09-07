"""
기업마당(bizinfo) 공고 수집 파이프라인 — Phase 1 검증용.

이 스크립트가 하는 일 (한 번에 하나씩, 순서대로):
  1. .env에서 BIZINFO_API_KEY를 읽는다 (절대 출력하지 않음).
  2. 목록 API를 여러 페이지 호출해 20건을 가져온다.
  3. 원본 응답을 그대로 보존한다 (원문 추적용).
  4. 내부 표준 구조로 변환한다 (Program + 사실단위 확인상태 태깅).
  5. pblancId(기업마당 고유 공고ID)를 기준으로 중복을 제거한다.
  6. 결과를 사람이 눈으로 검증할 수 있는 표로 정리해 출력/저장한다.
"""

import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.date_parsing import parse_application_period  # noqa: E402  (여러 기관이 공유하는 공통 로직)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

RAW_PAGES_DIR = PROJECT_ROOT / "collector" / "raw" / "bizinfo" / "pages"
RAW_ITEMS_DIR = PROJECT_ROOT / "collector" / "raw" / "bizinfo" / "items"
MAPPED_OUT_PATH = PROJECT_ROOT / "collector" / "mapped" / "bizinfo_mapped.json"

PAGE_UNIT = 10
PAGES_TO_FETCH = 2  # 10 x 2 = 20건


def load_env(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def fetch_page(api_key: str, page_index: int) -> dict:
    params = {
        "crtfcKey": api_key,
        "dataType": "json",
        "pageUnit": str(PAGE_UNIT),
        "pageIndex": str(page_index),
    }
    response = requests.get(API_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def compute_file_hash(path: Path) -> str:
    """
    이 프로젝트 전체에서 사용하는 단 하나의 원본 해시 계산 방법.
    파일을 재구성(직렬화)하지 않고, 디스크에 있는 바이트를 그대로 읽어
    SHA-256을 계산한다 — 키 정렬, 들여쓰기, 개행 방식 같은 "재직렬화 시
    달라질 수 있는 요소"에 전혀 영향받지 않는다. 규칙은
    docs/raw-data-hash-policy.md 에 문서화되어 있다.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_bytes(path: Path, data) -> Path:
    """
    json.dumps 결과를 바이트로 직접 인코딩해서 저장한다 (write_text 대신
    write_bytes 사용). write_text는 플랫폼에 따라 개행문자를 변환할 수
    있어(Windows: \\n -> \\r\\n) 같은 내용도 저장할 때마다 바이트가
    달라질 수 있다 — 그러면 "내용이 같으면 해시도 같다"는 원칙이 깨진다.
    write_bytes는 그런 변환이 없어 항상 동일한 바이트를 저장한다.
    """
    content_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(content_bytes)
    return path


def save_raw_page(page_index: int, payload: dict, collected_at: str) -> Path:
    RAW_PAGES_DIR.mkdir(parents=True, exist_ok=True)
    ts = collected_at.replace(":", "").replace("-", "").replace(" ", "_")
    path = RAW_PAGES_DIR / f"{ts}_page{page_index}.json"
    return _write_json_bytes(path, payload)


def save_raw_item(item: dict, collected_at: str) -> Path:
    """
    항목별 원본 스냅샷을 pblancId 폴더 아래 수집시각 파일명으로 저장한다.
    같은 공고를 나중에 다시 수집했을 때 내용이 바뀌었으면 새 파일이 하나 더
    쌓이므로, 파일 목록만 봐도 "언제 무엇이 바뀌었는지" 이력을 알 수 있다.
    """
    pblanc_id = item.get("pblancId", "UNKNOWN")
    item_dir = RAW_ITEMS_DIR / pblanc_id
    item_dir.mkdir(parents=True, exist_ok=True)
    ts = collected_at.replace(":", "").replace("-", "").replace(" ", "_")
    path = item_dir / f"{ts}.json"
    return _write_json_bytes(path, item)


def parse_attachments(file_names: str, file_urls: str):
    """
    fileNm / flpthNm은 여러 첨부파일이 있을 때 '@'로 이어붙여져 온다.
    두 목록의 순서가 대응된다고 가정하고 짝지어 정리한다(개수가 다르면 원문 그대로 보존).
    """
    names = file_names.split("@") if file_names else []
    urls = file_urls.split("@") if file_urls else []
    if len(names) != len(urls):
        return {"parsed": False, "raw_names": file_names, "raw_urls": file_urls}
    return {"parsed": True, "files": [{"name": n, "url": u} for n, u in zip(names, urls)]}


def guess_region_from_title(title: str):
    """
    지역은 API가 별도 필드로 주지 않는다. 제목 맨 앞의 '[지역]' 표기에서만
    '추정'한다 (예: "[경기] 안산시 ..." -> "경기").

    과거 버전은 이 표기가 없으면 소관기관명(jrsdInsttNm)을 그대로 지역으로
    썼는데, "지식재산처"처럼 지역이 아닌 중앙기관명이 그대로 지역인 것처럼
    표시되는 오류가 있었다 (데이터 품질 점검 2026-09-04, 문제 1). 기관명을
    지역으로 대체하는 방식은 더 이상 쓰지 않는다 — 표기가 없으면 None을
    반환하고, 호출부에서 "미추출"로 처리한다.
    """
    match = re.match(r"^\[(.+?)\]", title or "")
    return match.group(1) if match else None


def map_item_to_program(raw: dict, collected_at: str, raw_hash: str) -> dict:
    """
    기업마당 원본 필드 -> 내부 표준 구조(Program 요약 + 확인상태 태깅).
    각 값에 confirmation을 붙여, 'API가 직접 준 값'과 '우리가 계산/추정한 값'을
    화면 단계에서 구분해 표시할 수 있게 한다. (확인된 사실 / 추정)
    """
    period = parse_application_period(raw.get("reqstBeginEndDe", ""), date.today())
    attachments = parse_attachments(raw.get("fileNm", ""), raw.get("flpthNm", ""))
    region_guess = guess_region_from_title(raw.get("pblancNm", ""))

    return {
        "source": "bizinfo",
        "source_item_id": raw.get("pblancId"),  # 중복 제거 기준 키
        "fields": {
            "사업명": {"value": raw.get("pblancNm"), "confirmation": "확인된 사실"},
            "주관기관": {"value": raw.get("excInsttNm"), "confirmation": "확인된 사실"},
            "소관기관": {"value": raw.get("jrsdInsttNm"), "confirmation": "확인된 사실"},
            "대상기업": {"value": raw.get("trgetNm"), "confirmation": "확인된 사실"},
            "신청기간_원문": {"value": raw.get("reqstBeginEndDe"), "confirmation": "확인된 사실"},
            "신청기간_시작": {"value": period["start"], "confirmation": "확인된 사실" if period["is_structured"] else "해당없음"},
            "신청기간_종료": {"value": period["end"], "confirmation": "확인된 사실" if period["is_structured"] else "해당없음"},
            "공고상태": {"value": period["status"], "confirmation": "AI 분석(날짜 계산)"},
            "지원분야_대분류": {"value": raw.get("pldirSportRealmLclasCodeNm"), "confirmation": "확인된 사실"},
            "지원분야_중분류": {"value": raw.get("pldirSportRealmMlsfcCodeNm"), "confirmation": "확인된 사실"},
            "지역": {
                "value": region_guess,
                "confirmation": "추정(제목의 [지역] 표기 기반)" if region_guess else "미추출 — 제목에 지역 표기가 없어 확인 불가",
            },
            "지원금액": {"value": None, "confirmation": "미추출 — 사업요약 원문에 포함될 수 있음, Phase1은 자동추출 안 함"},
            "사업요약_HTML": {"value": raw.get("bsnsSumryCn"), "confirmation": "확인된 사실"},
            "신청방법": {"value": raw.get("reqstMthPapersCn"), "confirmation": "확인된 사실"},
            "문의처": {"value": raw.get("refrncNm"), "confirmation": "확인된 사실"},
        },
        "attachments": attachments,
        "source_document": {
            "원문_상세_URL": raw.get("pblancUrl"),
            "수집일": collected_at,
            "원본_해시": raw_hash,
        },
    }


def main() -> int:
    env = load_env(ENV_PATH)
    api_key = env.get("BIZINFO_API_KEY", "")
    if not api_key:
        print("[결과] 실패 — .env에 BIZINFO_API_KEY가 없습니다.")
        return 1

    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_raw_items = []
    for page_index in range(1, PAGES_TO_FETCH + 1):
        try:
            payload = fetch_page(api_key, page_index)
        except requests.exceptions.RequestException as exc:
            safe_message = re.sub(r"crtfcKey=[^&\s]+", "crtfcKey=****", str(exc))
            print(f"[결과] 실패 — page {page_index} 요청 중 오류: {safe_message}")
            return 1

        save_raw_page(page_index, payload, collected_at)
        items = payload.get("jsonArray", [])
        print(f"[정보] page {page_index}: {len(items)}건 수신")
        all_raw_items.extend(items)

    # 중복 제거: pblancId 기준
    seen_ids = set()
    unique_raw_items = []
    duplicate_count = 0
    for item in all_raw_items:
        pblanc_id = item.get("pblancId")
        if pblanc_id in seen_ids:
            duplicate_count += 1
            continue
        seen_ids.add(pblanc_id)
        unique_raw_items.append(item)

    print(f"[정보] 총 수집 {len(all_raw_items)}건 중 고유 공고 {len(unique_raw_items)}건 (중복 {duplicate_count}건 제거)")

    mapped_programs = []
    for item in unique_raw_items:
        item_path = save_raw_item(item, collected_at)
        item_hash = compute_file_hash(item_path)  # 저장된 파일 자체에서 계산 — 항상 파일과 일치
        mapped = map_item_to_program(item, collected_at, item_hash)
        mapped_programs.append(mapped)

    MAPPED_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAPPED_OUT_PATH.write_text(
        json.dumps(mapped_programs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[정보] 표준 구조 변환 결과 저장: {MAPPED_OUT_PATH} ({len(mapped_programs)}건)")

    # 사람이 눈으로 검증하기 쉬운 요약 표 출력
    print("\n[검증용 요약표]")
    print(f"{'ID':<24} {'사업명':<32} {'주관기관':<18} {'신청기간':<24} {'상태':<8}")
    print("-" * 110)
    for p in mapped_programs:
        f = p["fields"]
        title = (f["사업명"]["value"] or "")[:30]
        org = (f["주관기관"]["value"] or "")[:16]
        period = (f["신청기간_원문"]["value"] or "")[:22]
        status = f["공고상태"]["value"] or ""
        print(f"{p['source_item_id']:<24} {title:<32} {org:<18} {period:<24} {status:<8}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
