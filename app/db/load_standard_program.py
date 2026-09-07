"""
새 출처(기업마당 이외의 모든 어댑터)의 StandardProgram을 기존 DB 스키마에
적재하는 공용 로더.

app/db/load_bizinfo.py는 건드리지 않는다 — 기업마당은 계속 그 전용
파이프라인을 쓴다. 이 파일은 앞으로 추가되는 기관들(KOCCA, K-Startup, ...)
이 전부 공유하는 두 번째 경로다.

이 파일 자체는 어떤 외부 API도 호출하지 않는다. 순수하게 이미 만들어진
StandardProgram + 원본 raw dict를 받아 DB에 쓰기만 한다.
"""

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_bizinfo import get_or_create_organization, get_relationship_type_id  # noqa: E402  (재사용, 수정 없음)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "collector"))
from adapters.base import StandardProgram  # noqa: E402
from common.date_parsing import parse_application_period  # noqa: E402

from datetime import date


def _compute_status(program: StandardProgram) -> str:
    """StandardProgram엔 상태 필드가 없어서, 있는 날짜 정보로 다시 계산한다."""
    if program.application_start and program.application_end:
        # parse_application_period가 'YYYY-MM-DD ~ YYYY-MM-DD' 형태를 기대하므로 재조합
        period_text = f"{program.application_start} ~ {program.application_end}"
        return parse_application_period(period_text, date.today())["status"]
    return "비정형(원문 참조)" if program.application_period_raw else "정보없음"


def load_standard_program(conn, program: StandardProgram, raw_item: Optional[dict] = None) -> str:
    """
    반환값: 'inserted' / 'updated' / 'unchanged' (load_bizinfo.load_program과 동일한 관례)
    """
    existing = conn.execute(
        "SELECT id, latest_raw_hash FROM programs WHERE source = ? AND source_item_id = ?",
        (program.source, program.source_program_id),
    ).fetchone()

    if existing and existing[1] == program.content_hash and program.content_hash:
        return "unchanged"

    status_computed = _compute_status(program)

    if existing:
        program_id = existing[0]
        conn.execute(
            """
            UPDATE programs SET
              title = ?, status_computed = ?, application_period_display = ?,
              target_company_display = ?, last_updated_at = ?, latest_raw_hash = ?
            WHERE id = ?
            """,
            (program.title, status_computed, program.application_period_raw,
             program.target_raw, program.collected_at, program.content_hash, program_id),
        )
        outcome = "updated"
    else:
        cur = conn.execute(
            """
            INSERT INTO programs (
              source, source_item_id, title, status_computed, application_period_display,
              amount_display, target_company_display, region_display,
              first_collected_at, last_updated_at, latest_raw_hash
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?)
            """,
            (program.source, program.source_program_id, program.title, status_computed,
             program.application_period_raw, program.target_raw,
             program.collected_at, program.collected_at, program.content_hash),
        )
        program_id = cur.lastrowid
        outcome = "inserted"

    # 기관 연결 — load_bizinfo.py의 기존 함수를 그대로 재사용 (기초자치단체 등
    # 비-기관명 블랙리스트도 동일하게 적용됨)
    org_id = get_or_create_organization(conn, program.organization)
    if org_id:
        role_id = get_relationship_type_id(conn, "주관")
        conn.execute(
            "INSERT OR IGNORE INTO program_organization_roles (program_id, org_id, role_type_id) VALUES (?, ?, ?)",
            (program_id, org_id, role_id),
        )

    # 원문 웹페이지 출처 문서
    webpage_doc_id = conn.execute(
        """
        INSERT INTO source_documents (program_id, document_type, source_org, url, collected_at, content_hash)
        VALUES (?, '웹페이지', ?, ?, ?, ?)
        """,
        (program_id, program.source, program.source_url, program.collected_at, program.content_hash),
    ).lastrowid

    # 원본 응답 보존 (raw_api_responses) — 기존에는 이 표에 아예 쓰지
    # 않아서 programs/source_documents의 해시와 어긋나 있었다(2026-09-07
    # test_hash_consistency.py 4번 검사에서 발견). raw_item이 주어졌을
    # 때만 기록하고, content_hash는 반드시 program.content_hash와
    # 동일한 값을 쓴다 — 해시 계산 방식은 하나로 통일한다는 기존 원칙
    # (raw-data-hash-policy.md)을 그대로 따른다. 이미 같은 해시로
    # 저장된 적이 있으면 다시 넣지 않는다(멱등성).
    if raw_item is not None:
        already_saved = conn.execute(
            """
            SELECT id FROM raw_api_responses
            WHERE source = ? AND source_item_id = ? AND response_type = 'item' AND content_hash = ?
            """,
            (program.source, program.source_program_id, program.content_hash),
        ).fetchone()
        if not already_saved:
            conn.execute(
                """
                INSERT INTO raw_api_responses (source, source_item_id, response_type, raw_json, collected_at, content_hash)
                VALUES (?, ?, 'item', ?, ?, ?)
                """,
                (
                    program.source,
                    program.source_program_id,
                    json.dumps(raw_item, ensure_ascii=False, sort_keys=True),
                    program.collected_at,
                    program.content_hash,
                ),
            )

    for url in program.attachment_urls:
        file_name = url.rsplit("/", 1)[-1] or "첨부파일"
        conn.execute(
            """
            INSERT INTO source_documents (program_id, document_type, source_org, url, file_name, collected_at)
            VALUES (?, '첨부파일', ?, ?, ?, ?)
            """,
            (program_id, program.source, url, file_name, program.collected_at),
        )

    # 사실 단위 필드 (program_fields) — 있는 값만, 없으면 정직하게 '미추출'
    fields = [
        ("사업명", program.title, "확인된 사실" if program.title else "미추출"),
        ("주관기관", program.organization, "확인된 사실" if program.organization else "미추출"),
        ("신청기간_원문", program.application_period_raw, "확인된 사실" if program.application_period_raw else "미추출"),
        ("신청기간_시작", program.application_start, "확인된 사실" if program.application_start else "해당없음"),
        ("신청기간_종료", program.application_end, "확인된 사실" if program.application_end else "해당없음"),
        ("공고상태", status_computed, "AI 분석(날짜 계산)"),
        ("대상기업", program.target_raw, "확인된 사실" if program.target_raw else "미추출"),
        ("지원금액", None, "미추출 — 이 출처의 응답에 구조화된 금액 필드가 없음(확인 필요)"),
        ("지역", None, "미추출 — 이 출처는 아직 지역 추정 로직이 없음"),
        ("사업요약_HTML", program.summary_raw, "확인된 사실" if program.summary_raw else "미추출"),
    ]
    from load_bizinfo import normalize_confirmation  # noqa: E402  (재사용)

    for field_name, value, raw_confirmation in fields:
        confirmation, note = normalize_confirmation(raw_confirmation)
        conn.execute(
            """
            INSERT INTO program_fields (
              program_id, field_name, field_value, confirmation_status,
              source_document_id, section_text, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (program_id, field_name, value, confirmation, webpage_doc_id, note, program.collected_at),
        )

    return outcome
