"""
K-Startup(창업진흥원) "지원사업 공고 정보"(getAnnouncementInformation01) API
연결 테스트 스크립트 — 공식 가이드 문서(서비스설계서 v2.0)를 직접 읽고
확인한 요청 URL·파라미터 기준으로 작성했다.

원칙: 이 스크립트는 API 키 값을 절대 출력/로그에 남기지 않는다.
perPage=5로 제한해 한 번에 최대 5건만 요청한다.
"""

import json
import re
import sys
import urllib.parse
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# 가이드 문서 "Call Back URL(외부노출URL)" 그대로 (서비스설계서 v2.0, 표 7)
API_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"


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


def mask(value: str) -> str:
    if not value:
        return "(비어있음)"
    return f"(길이 {len(value)}자, ****로 마스킹됨)"


def mask_url(url: str) -> str:
    return re.sub(r"(ServiceKey=)[^&\s]+", r"\1****", url)


def main() -> int:
    env = load_env(ENV_PATH)
    api_key = env.get("KSTARTUP_API_KEY", "")

    if not api_key:
        print("[결과] 실패 — .env에 KSTARTUP_API_KEY 값이 비어있습니다.")
        return 1

    print(f"[정보] KSTARTUP_API_KEY 확인됨 {mask(api_key)} — 값 자체는 출력하지 않습니다.")

    # 가이드(표 8) 요청 파라미터: ServiceKey(필수, URL Encode), page, perPage, returnType 등
    # .env에 저장된 값이 이미 공공데이터포털의 "Encoding" 형태(%2B, %3D 등 포함)로
    # 보여, requests의 params=에 넣지 않고 완성된 쿼리스트링을 직접 만들어 붙인다
    # (params=에 넣으면 이미 인코딩된 값을 다시 인코딩해버려 깨질 수 있음).
    query = (
        f"ServiceKey={api_key}"
        f"&page=1"
        f"&perPage=5"
        f"&returnType=json"
    )
    full_url = f"{API_URL}?{query}"

    print(f"[정보] 요청 URL(마스킹됨): {mask_url(full_url)}")

    try:
        response = requests.get(full_url, timeout=10)
    except requests.exceptions.RequestException as exc:
        safe_message = re.sub(r"(ServiceKey=)[^&\s]+", r"\1****", str(exc))
        print("[결과] 실패 — 네트워크 요청 중 오류 발생")
        print(f"[오류 내용] {safe_message}")
        return 1

    print(f"[정보] HTTP 상태 코드: {response.status_code}")
    content_type = response.headers.get("Content-Type", "")
    print(f"[정보] 응답 Content-Type: {content_type}")

    body_text = response.text
    safe_body_preview = re.sub(r"(ServiceKey=)[^&\s\"<]+", r"\1****", body_text)

    if response.status_code != 200:
        print("[결과] 실패 — API가 200이 아닌 상태 코드를 반환했습니다.")
        print(f"[응답 본문 일부 (키 마스킹됨)]\n{safe_body_preview[:1500]}")
        return 1

    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        print("[결과] 실패 — 응답을 JSON으로 해석할 수 없습니다 (XML로 왔을 가능성).")
        print(f"[응답 본문 일부 (키 마스킹됨)]\n{safe_body_preview[:1500]}")
        return 1

    # 공공데이터포털 표준 에러 응답 형태 확인 (가이드 "2. OpenAPI 에러 코드정리" 참고)
    if isinstance(data, dict) and "resultCode" in data and str(data.get("resultCode")) not in ("00", "0"):
        print("[결과] 실패 — API가 에러를 반환했습니다.")
        print(f"[에러 내용] resultCode={data.get('resultCode')} resultMsg={data.get('resultMsg')}")
        return 1

    print("[결과] 성공 — JSON 응답을 받았습니다.")

    raw_dump_path = PROJECT_ROOT / "collector" / "sample_kstartup_response.json"
    raw_dump_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[정보] 원본 응답을 저장했습니다: {raw_dump_path}")

    # 응답 구조 요약
    if isinstance(data, dict):
        print("[정보] 최상위 키 목록:", list(data.keys()))
        items = None
        for key in ("data", "items", "response"):
            if key in data:
                items = data[key]
                break
        if isinstance(items, list):
            print(f"[정보] 항목(items) 개수: {len(items)}")
            if items:
                print("[정보] 첫 항목의 필드명:", sorted(items[0].keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
