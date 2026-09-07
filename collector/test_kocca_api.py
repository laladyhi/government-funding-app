"""
한국콘텐츠진흥원(KOCCA) 지원사업 API 실 호출 테스트 스크립트 (최대 5건, 1회 호출).

사용자가 첨부한 공식 명세서(한국콘텐츠진흥원_지원사업_API_명세서.pdf) 기준.
이 스크립트는 그 명세서 기준 URL/파라미터/필드명이 실제 응답과 맞는지
"확인"하는 단계다 — 아직 어댑터(collector/adapters/kocca_adapter.py)를
고치지 않는다(확인 후 별도로 반영).

명세서에서 발견된 내부 불일치(주의):
  - 요청변수 표: startDt/endDt.  샘플 URL: viewStartDt.
  - 응답필드 표: regDate.        샘플 JSON: regDt.
  둘 중 어느 쪽이 실제인지는 이번 실제 호출 결과로 확인한다(추측하지 않음).
  이번 호출에는 날짜 파라미터를 아예 넣지 않으므로 요청 쪽 불일치는
  이번 테스트와 무관하다 — 응답 쪽(regDate vs regDt)만 실제로 확인된다.

.env에 KOCCA_API_KEY가 없으면 아무 것도 호출하지 않는다
(check_readiness() 규칙을 그대로 따름 — 이 스크립트는 자체적으로도
한 번 더 키 존재 여부를 확인한다).

이 스크립트는 API 키 값을 절대 출력하지 않는다. 원본 응답은 운영/정식
경로(collector/raw/kocca/)가 아니라 테스트용 위치(collector/sample_kocca_response.json)
에만 저장한다. 운영 DB는 열지 않는다.

실행: python collector/test_kocca_api.py
"""

import json
import sys
import urllib.parse
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.env import get_env_value  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUEST_URL = "https://kocca.kr/api/pims/List.do"
ENV_VAR_NAME = "KOCCA_API_KEY"
NUM_OF_ROWS = 5

SAMPLE_OUT_PATH = PROJECT_ROOT / "collector" / "sample_kocca_response.json"


def mask(value: str) -> str:
    if not value:
        return "(비어있음)"
    return f"(길이 {len(value)}자, ****로 마스킹됨)"


def main() -> int:
    api_key = get_env_value(ENV_VAR_NAME)
    print(f"[정보] {ENV_VAR_NAME} 확인됨 {mask(api_key)} — 값 자체는 출력하지 않습니다.")

    if not api_key:
        print("[결과] 실패 — .env에 KOCCA_API_KEY가 없어 실제 호출을 하지 않습니다.")
        return 1

    # 조건 6: 키가 이미 URL 인코딩되어 있으면(%가 포함되어 있으면) 그대로
    # 쿼리스트링 끝에 붙이고, requests의 params=에는 절대 넣지 않는다
    # (넣으면 다시 인코딩되어 이중 인코딩됨 — 정부24 때 겪은 문제와 동일).
    # 인코딩되어 있지 않은 평문 키라면 params=에 정상적으로 넣어도 안전하다.
    base_params = {"numOfRows": NUM_OF_ROWS}
    if "%" in api_key:
        query = urllib.parse.urlencode(base_params)
        full_url = f"{REQUEST_URL}?{query}&serviceKey={api_key}"
        print("[정보] 서비스키가 이미 URL 인코딩된 형태로 보여, 쿼리스트링에 직접 이어붙입니다(이중 인코딩 방지).")
        response = requests.get(full_url, timeout=10)
    else:
        params = dict(base_params)
        params["serviceKey"] = api_key
        print("[정보] 서비스키가 평문 형태로 보여, requests의 정상 파라미터 인코딩을 사용합니다.")
        response = requests.get(REQUEST_URL, params=params, timeout=10)

    print(f"[정보] HTTP 상태 코드: {response.status_code}")

    if response.status_code != 200:
        safe_text = response.text[:300].replace(api_key, "****")
        print(f"[결과] 실패 — HTTP {response.status_code}. 응답 일부: {safe_text}")
        return 1

    try:
        data = response.json()
    except ValueError:
        safe_text = response.text[:300].replace(api_key, "****")
        print(f"[결과] 실패 — JSON 파싱 실패. 응답 일부(마스킹): {safe_text}")
        return 1

    info = data.get("INFO", {})
    result_code = info.get("resultCode")
    # 명세서 필드표는 resultMsg, 명세서 샘플JSON은 resultMgs(오타로 보임) —
    # 실제 응답에서 어느 쪽이 나오는지 둘 다 확인해서 보여준다(추측 없이).
    result_msg = info.get("resultMsg", info.get("resultMgs"))
    items = info.get("list", [])
    list_count = info.get("listCount")

    print(f"\n[확인] INFO.resultCode = {result_code!r}")
    print(f"[확인] INFO.resultMsg(또는 resultMgs) = {result_msg!r}")
    print(f"[확인] INFO.listCount = {list_count!r}")
    print(f"[확인] INFO.list 길이 = {len(items)}")

    if result_code and result_code != "INFO-000":
        print(f"[결과] API가 오류 응답을 반환했습니다 — resultCode={result_code}, resultMsg={result_msg}")
        return 1

    if not items:
        print("[결과] 인증은 성공했으나 수신 항목이 0건입니다.")
        return 0

    # INFO 최상위에 남는 키(list 제외) — 응답 전체 구조를 있는 그대로 보여준다.
    top_level_keys = sorted(info.keys())
    print(f"\n[확인] INFO 최상위 키 전체: {top_level_keys}")
    first_item_keys = sorted(items[0].keys())
    print(f"[확인] 목록 항목(list[0])의 실제 필드명: {first_item_keys}")

    print(f"\n[미리보기] 수신 {len(items)}건 (제목 / 링크 일부)")
    for item in items:
        print(f"  - {item.get('title')!r}")
        print(f"    link: {item.get('link')!r}")

    SAMPLE_OUT_PATH.write_bytes(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    )
    print(f"\n[정보] 원본 응답을 테스트용 위치에 저장했습니다(운영 경로 아님): {SAMPLE_OUT_PATH}")
    print("[정보] 운영 DB에는 아무것도 쓰지 않았습니다(이 스크립트는 DB를 열지 않습니다).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
