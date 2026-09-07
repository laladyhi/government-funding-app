"""
기업마당(bizinfo.go.kr) Open API 연결 테스트 스크립트.

목적: .env의 BIZINFO_API_KEY를 읽어 실제로 API가 응답하는지 확인한다.
원칙: 이 스크립트는 API 키 값을 절대 출력/로그에 남기지 않는다.
"""

import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

# Windows 콘솔(cp949)에서도 한글/특수문자가 깨지지 않도록 출력 인코딩을 강제한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"


def load_env(path: Path) -> dict:
    """.env 파일을 외부 라이브러리 없이 직접 파싱한다 (KEY=VALUE 형식)."""
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
    """로그에 남길 때 키 값을 절대 노출하지 않기 위한 마스킹."""
    if not value:
        return "(비어있음)"
    return f"(길이 {len(value)}자, ****로 마스킹됨)"


def main() -> int:
    env = load_env(ENV_PATH)
    api_key = env.get("BIZINFO_API_KEY", "")

    if not api_key:
        print("[결과] 실패 — .env에 BIZINFO_API_KEY 값이 비어있습니다.")
        return 1

    print(f"[정보] API 키 확인됨 {mask(api_key)} — 값 자체는 출력하지 않습니다.")

    params = {
        "crtfcKey": api_key,
        "dataType": "json",
        "pageUnit": "10",
        "pageIndex": "1",
    }

    # 로그용 URL은 키를 마스킹해서만 표시한다 (실제 요청에는 정상 키 사용)
    masked_params = {**params, "crtfcKey": "****"}
    print(f"[정보] 요청 URL(마스킹됨): {API_URL}?{urllib.parse.urlencode(masked_params)}")

    try:
        response = requests.get(API_URL, params=params, timeout=10)
    except requests.exceptions.RequestException as exc:
        # 예외 메시지에 URL이 포함될 수 있어 키 부분을 마스킹 후 출력
        safe_message = re.sub(r"crtfcKey=[^&\s]+", "crtfcKey=****", str(exc))
        print("[결과] 실패 — 네트워크 요청 중 오류 발생")
        print(f"[오류 내용] {safe_message}")
        return 1

    print(f"[정보] HTTP 상태 코드: {response.status_code}")

    body_text = response.text
    safe_body_preview = re.sub(r"crtfcKey=[^&\s\"<]+", "crtfcKey=****", body_text)

    if response.status_code != 200:
        print("[결과] 실패 — API가 200이 아닌 상태 코드를 반환했습니다.")
        print(f"[응답 본문 일부 (키 마스킹됨)]\n{safe_body_preview[:1000]}")
        return 1

    content_type = response.headers.get("Content-Type", "")
    print(f"[정보] 응답 Content-Type: {content_type}")

    # JSON 파싱 시도
    try:
        data = response.json()
        print("[결과] 성공 — JSON 응답을 받았습니다.")
        print("[정보] 최상위 키 목록:", list(data.keys()) if isinstance(data, dict) else type(data))

        raw_dump_path = PROJECT_ROOT / "collector" / "sample_response.json"
        raw_dump_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[정보] 원본 응답을 저장했습니다: {raw_dump_path}")
        return 0
    except (json.JSONDecodeError, ValueError):
        pass

    # XML 파싱 시도 (dataType=json이 무시되고 XML로 오는 API가 많음)
    try:
        root = ET.fromstring(body_text)
        print("[결과] 성공 — XML 응답을 받았습니다 (JSON 파라미터가 무시된 것으로 보임).")
        print(f"[정보] 루트 태그: {root.tag}")
        child_tags = sorted({child.tag for child in root.iter()})
        print(f"[정보] 응답에 포함된 태그 목록(최대 30개): {child_tags[:30]}")

        raw_dump_path = PROJECT_ROOT / "collector" / "sample_response.xml"
        raw_dump_path.write_text(body_text, encoding="utf-8")
        print(f"[정보] 원본 응답을 저장했습니다: {raw_dump_path}")
        return 0
    except ET.ParseError:
        pass

    print("[결과] 실패 — 응답을 JSON/XML 어느 쪽으로도 해석할 수 없습니다.")
    print(f"[응답 본문 일부 (키 마스킹됨)]\n{safe_body_preview[:1000]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
