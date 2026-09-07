"""
정부24 공공서비스(혜택) API 실 호출 테스트 스크립트 (최대 5건).

.env에 PUBLIC_BENEFITS_API_KEY가 없으면 아무 것도 호출하지 않고
안내만 출력한다 (adapter의 check_readiness() 규칙을 그대로 따름).
키가 있으면 serviceList를 perPage=5로 딱 1번 호출한다.

이 스크립트는 API 키 값을 절대 출력하지 않는다.

실행: python collector/test_public_benefits_api.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import ReadinessStatus  # noqa: E402
from adapters.public_benefits_adapter import PublicBenefitsAdapter  # noqa: E402
from common.env import get_env_value  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mask(value: str) -> str:
    if not value:
        return "(비어있음)"
    return f"(길이 {len(value)}자, ****로 마스킹됨)"


def main() -> int:
    adapter = PublicBenefitsAdapter()
    readiness = adapter.check_readiness()

    api_key_len_info = mask(get_env_value(adapter.env_var_name))
    print(f"[정보] {adapter.env_var_name} 확인됨 {api_key_len_info} — 값 자체는 출력하지 않습니다.")
    print(f"[정보] 준비 상태: {readiness.value}")

    if readiness != ReadinessStatus.READY:
        print("[결과] 실패 — 키가 없어 실제 호출을 하지 않습니다. "
              ".env에 PUBLIC_BENEFITS_API_KEY를 넣은 뒤 다시 실행하세요.")
        return 1

    print("[정보] serviceList를 perPage=5로 1회만 호출합니다...")
    items = adapter.fetch_list(page=1, page_size=5)

    if not items:
        print("[결과] 실패 또는 결과 0건 — collector/logs/public_benefits_errors.jsonl 확인 필요.")
        return 1

    print(f"[결과] 성공 — {len(items)}건 수신")
    print("[정보] 첫 항목의 필드명:", sorted(items[0].keys()))

    raw_dump_path = PROJECT_ROOT / "collector" / "sample_public_benefits_response.json"
    raw_dump_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[정보] 원본 응답을 저장했습니다: {raw_dump_path}")

    print("\n[미리보기] (변환 전 원문 일부)")
    for item in items:
        print(f"  - {item.get('서비스ID')}: {item.get('서비스명')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
