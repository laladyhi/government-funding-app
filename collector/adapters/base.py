"""
모든 기관 어댑터가 따르는 공통 규칙 (인터페이스).

새 기관을 추가할 때 이 파일을 고칠 필요는 없다 — 이 파일이 정의하는
약속(SourceAdapter, StandardProgram)을 지키는 새 어댑터 파일 하나만
collector/adapters/ 아래에 추가하면 된다. 자세한 절차는
docs/adding-new-source.md 참고.

이 파일 자체는 어떤 외부 API도 호출하지 않는다 (순수 파이썬 구조 정의).
"""

import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "collector" / "logs"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.env import get_env_value  # noqa: E402


class ReadinessStatus(str, Enum):
    """
    실제 API를 호출하기 전에 반드시 확인하는 상태.
    READY가 아니면 어댑터는 fetch_list()를 호출하면 안 된다.
    """

    READY = "준비됨"
    MISSING_KEY = "승인 대기 또는 키 미설정"
    LINK_ONLY = "링크만관리(자동수집 대상 아님)"


@dataclass
class AttachmentRef:
    name: str
    url: str


@dataclass
class StandardProgram:
    """
    모든 출처(기업마당, 한국콘텐츠진흥원, K-Startup, ...)가 공통으로
    맞춰야 하는 내부 표준 구조. 어댑터의 to_standard_program()은 항상
    이 구조를 반환한다.

    신청기간이 날짜 형식이 아니면(예: "수시접수") application_start/end는
    반드시 None으로 둔다 — 억지로 날짜를 만들어내지 않는다.
    """

    source: str                       # 예: 'bizinfo', 'kocca', 'kstartup'
    source_program_id: str            # 출처 내 고유 ID
    title: str
    organization: Optional[str]
    application_period_raw: Optional[str]
    application_start: Optional[str]  # 'YYYY-MM-DD' 또는 None
    application_end: Optional[str]
    target_raw: Optional[str]
    summary_raw: Optional[str]
    source_url: Optional[str]
    attachment_urls: List[str] = field(default_factory=list)
    collected_at: str = ""
    content_hash: str = ""

    def dedup_key(self) -> tuple:
        """출처 내 중복 제거 기준 키 — (source, source_program_id)."""
        return (self.source, self.source_program_id)


class SourceAdapter(ABC):
    """
    기관별 어댑터가 공통으로 구현해야 하는 5가지:
      1) fetch_list      - 목록 조회
      2) to_standard_program - 상세 변환
      3) extract_attachments - 첨부파일 처리
      4) (StandardProgram 자체가) 원문 출처 저장에 필요한 값을 담음
      5) log_error        - 오류 기록
    """

    source_key: str = ""
    env_var_name: Optional[str] = None  # 링크만관리 출처는 None

    def check_readiness(self) -> ReadinessStatus:
        """
        네트워크 호출 없이 "지금 이 어댑터를 실행해도 되는가"만 확인한다.
        환경변수가 없거나 비어있으면 절대 fetch_list()를 호출하면 안 된다.
        """
        if self.env_var_name is None:
            return ReadinessStatus.LINK_ONLY
        value = get_env_value(self.env_var_name).strip()
        if not value:
            return ReadinessStatus.MISSING_KEY
        return ReadinessStatus.READY

    @abstractmethod
    def fetch_list(self, page: int = 1, page_size: int = 10) -> List[dict]:
        """
        목록 조회. 원본 그대로의 dict 리스트를 반환한다(아직 변환하지 않음).
        구현체는 반드시 시작 부분에서 check_readiness()가 READY인지 먼저
        확인해야 한다 — 이 메서드 자체는 그 확인을 강제하지 않으므로,
        호출하는 쪽(실행 스크립트)이 항상 먼저 check_readiness()를 부른다.
        """
        raise NotImplementedError

    @abstractmethod
    def to_standard_program(self, raw_item: dict) -> StandardProgram:
        """원문 1건 -> StandardProgram. 순수 변환 함수(네트워크 호출 없음)."""
        raise NotImplementedError

    def extract_attachments(self, raw_item: dict) -> List[AttachmentRef]:
        """
        기본 구현은 빈 리스트 — 첨부파일이 있는 출처만 override한다.
        """
        return []

    def log_error(self, stage: str, message: str, raw_context: Optional[dict] = None) -> None:
        """
        오류를 collector/logs/{source_key}_errors.jsonl 에 한 줄씩 남긴다.
        DB 연결 없이도 동작해서, 어댑터 자체는 항상 DB와 무관하게 테스트할
        수 있다.
        """
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{self.source_key}_errors.jsonl"
        entry = {
            "source": self.source_key,
            "stage": stage,
            "message": message,
            "context": raw_context or {},
            "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
