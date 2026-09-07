"""
.env 파일을 읽는 공통 유틸리티.

이 프로젝트는 python-dotenv 같은 라이브러리를 쓰지 않고, 지금까지도
(collector/fetch_and_store.py, collector/test_bizinfo_api.py) 항상 .env
파일을 직접 파싱해왔다. 여러 어댑터가 이 방식을 그대로 재사용하도록
여기 하나로 모았다 — 실제 셸(운영체제) 환경변수가 아니라 .env 파일
내용을 기준으로 한다는 점이 중요하다 (os.environ만 보면 .env 파일에
값이 있어도 못 찾는다).

이 파일은 키 값을 출력하지 않는다. 어디서도 값을 print()하지 않도록
호출하는 쪽에서도 주의할 것.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_env_file(path: Path = ENV_PATH) -> dict:
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


def get_env_value(name: str) -> str:
    """지정한 변수 하나의 값만 돌려준다. 없으면 빈 문자열."""
    return load_env_file().get(name, "")
