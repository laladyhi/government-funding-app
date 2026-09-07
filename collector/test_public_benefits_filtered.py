"""
정부24 공공서비스(혜택) API 실 호출 테스트 스크립트 — 사용자구분 필터링 (최대 2회 호출).

목적: 이전(collector/test_public_benefits_api.py)에는 필터 없이 1회 호출해
개인/가구 대상 혜택만 나왔다. 이번에는 기업 관련 데이터가 있는지 확인하기
위해 사용자구분으로 필터링해서 딱 2번만 호출한다.

호출 내역(이 스크립트가 실행하는 전부):
  1) serviceList, cond[사용자구분::LIKE]=기업,      perPage=5
  2) serviceList, cond[사용자구분::LIKE]=소상공인,  perPage=5

.env에 PUBLIC_BENEFITS_API_KEY가 없으면 아무 것도 호출하지 않는다
(adapter의 check_readiness() 규칙을 그대로 따름).

운영 DB(app/data/govfunding.sqlite3)에는 절대 쓰지 않는다 — 이 스크립트는
호출 결과를 화면에 표시만 한다.

이 스크립트는 API 키 값을 절대 출력하지 않는다.

실행: python collector/test_public_benefits_filtered.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import ReadinessStatus  # noqa: E402
from adapters.public_benefits_adapter import PublicBenefitsAdapter  # noqa: E402
from common.env import get_env_value  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DISPLAY_FIELDS = ["서비스명", "사용자구분", "지원대상", "지원내용", "소관기관명"]
FILTERS = ["기업", "소상공인"]


def mask(value: str) -> str:
    if not value:
        return "(비어있음)"
    return f"(길이 {len(value)}자, ****로 마스킹됨)"


def print_item(item: dict):
    for field in DISPLAY_FIELDS:
        print(f"    {field}: {item.get(field)!r}")
    print()


def main() -> int:
    adapter = PublicBenefitsAdapter()
    readiness = adapter.check_readiness()

    api_key_len_info = mask(get_env_value(adapter.env_var_name))
    print(f"[정보] {adapter.env_var_name} 확인됨 {api_key_len_info} — 값 자체는 출력하지 않습니다.")
    print(f"[정보] 준비 상태: {readiness.value}")

    if readiness != ReadinessStatus.READY:
        print("[결과] 실패 — 키가 없어 실제 호출을 하지 않습니다.")
        return 1

    call_count = 0
    for keyword in FILTERS:
        call_count += 1
        print(f"\n=== 호출 {call_count}/2: cond[사용자구분::LIKE]={keyword}, perPage=5 ===")
        items = adapter.fetch_list(
            page=1,
            page_size=5,
            cond={"cond[사용자구분::LIKE]": keyword},
        )
        if not items:
            print(f"  결과 0건 (또는 실패 — collector/logs/public_benefits_errors.jsonl 확인 필요)")
            continue
        print(f"  {len(items)}건 수신")
        for idx, item in enumerate(items, start=1):
            print(f"  [{idx}]")
            print_item(item)

    print(f"[정보] 총 API 호출 횟수: {call_count}회 (제한: 최대 2회)")
    print("[정보] 운영 DB에는 아무것도 쓰지 않았습니다(이 스크립트는 DB를 열지 않습니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
