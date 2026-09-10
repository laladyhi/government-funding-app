"""NTIS 승인키와 public_project XML 응답을 1회, 최대 5건으로 확인한다."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])
from adapters.base import ReadinessStatus  # noqa: E402
from adapters.ntis_adapter import NtisAdapter  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword", default="창업")
    args = parser.parse_args()
    adapter = NtisAdapter()
    readiness = adapter.check_readiness()
    print(f"[정보] NTIS API 키 상태: {readiness.value}")
    if readiness != ReadinessStatus.READY:
        print("[결과] 실제 호출을 하지 않았습니다. .env의 NTIS_API_KEY를 확인하세요.")
        return 1
    xml_text = adapter.fetch_response(args.keyword, display_count=5)
    if xml_text:
        preview_path = Path(__file__).resolve().parent / "logs" / "ntis_last_response_preview.txt"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(xml_text[:2000], encoding="utf-8")
    items = adapter.parse_items(xml_text) if xml_text else []
    if not items:
        print(f"[결과] 실패 - {adapter.last_error or '응답이 없습니다.'}")
        if xml_text:
            print("[안내] NTIS 응답 일부를 collector\\logs\\ntis_last_response_preview.txt에 저장했습니다.")
        return 1
    print(f"[결과] 성공 — {len(items)}건 수신")
    for item in items:
        print(f"- {item.get('project_number')}: {item.get('title', '')[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
