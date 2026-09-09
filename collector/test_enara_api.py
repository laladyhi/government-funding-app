"""e나라도움 API 연결 테스트. 기본은 최대 5건이며 운영 DB를 변경하지 않는다."""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import ReadinessStatus  # noqa: E402
from adapters.enara_adapter import (  # noqa: E402
    EnaraAdapter,
    extract_items,
    extract_response_code,
    extract_response_message,
    extract_total_count,
)
from common.env import get_env_value  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    adapter = EnaraAdapter()
    readiness = adapter.check_readiness()
    print(f"[정보] ENARA_API_KEY 상태: {readiness.value}")
    if readiness != ReadinessStatus.READY:
        print("[결과] 키가 없어 실제 호출하지 않았습니다. 키 값은 채팅에 보내지 마세요.")
        return 1
    current_year = datetime.now().year
    business_year = current_year
    response = adapter.fetch_list_response(page=1, page_size=5, business_year=business_year)
    if not response:
        print(f"[결과] 실패 — {adapter.last_error or 'API 응답이 없습니다.'}")
        return 1
    code = extract_response_code(response)
    message = extract_response_message(response)
    items = extract_items(response)
    total = extract_total_count(response)
    # 사업연도는 필수값이고, 현재 연도에 아직 공고가 없을 수 있다.
    # 이 경우 직전 연도를 한 번만 확인해 "연결 실패"와 "해당 연도 0건"을 구분한다.
    if code == "00" and not items and total == 0:
        previous_year = current_year - 1
        previous_response = adapter.fetch_list_response(page=1, page_size=5, business_year=previous_year)
        if previous_response:
            previous_code = extract_response_code(previous_response)
            previous_items = extract_items(previous_response)
            previous_total = extract_total_count(previous_response)
            if previous_code == "00" and (previous_items or previous_total > 0):
                response = previous_response
                business_year = previous_year
                code = previous_code
                message = extract_response_message(response)
                items = previous_items
                total = previous_total
    print(f"[진단] 조회 사업연도: {business_year}")
    print(f"[진단] 응답코드: {code or '없음'}")
    print(f"[진단] 응답메시지: {message or '없음'}")
    if code and code != "00":
        print(f"[결과] 실패 — API가 오류를 반환했습니다: {code} {message}")
        print("[정보] 운영 DB에는 저장하지 않았습니다.")
        return 1
    print(f"[결과] 응답 성공 — 첫 페이지 {len(items)}건, 전체 {total}건")
    if not items and total == 0:
        print("[안내] API 연결과 인증은 정상입니다. 다만 현재 사업연도에는 조회 가능한 공고가 0건입니다.")
    if isinstance(response, dict):
        print(f"[진단] 최상위 응답 항목: {', '.join(sorted(response.keys()))}")
        if isinstance(response.get("header"), dict):
            print(f"[진단] header 항목: {', '.join(sorted(response['header'].keys()))}")
        body = response.get("body")
        if isinstance(body, dict):
            print(f"[진단] body 항목: {', '.join(sorted(body.keys()))}")
        nested = response.get("response")
        if isinstance(nested, dict):
            print(f"[진단] response 항목: {', '.join(sorted(nested.keys()))}")
            if isinstance(nested.get("header"), dict):
                print(f"[진단] 응답코드: {nested['header'].get('resultCode', '없음')}")
            if isinstance(nested.get("body"), dict):
                print(f"[진단] response.body 항목: {', '.join(sorted(nested['body'].keys()))}")
    if items:
        print(f"[정보] 응답 필드: {', '.join(sorted(items[0].keys()))}")
        for item in items:
            program = adapter.to_standard_program(item)
            print(f"  - {program.source_program_id}: {program.title[:80]}")
    print("[정보] 운영 DB에는 저장하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
