"""
Government Funding AI — Phase 1 로컬 웹 서버 (Flask).

실행: python app/server.py
접속: http://127.0.0.1:5000

화면:
  /                       -> /programs 로 이동
  /programs               -> 목록 + 검색 + 필터 (화면설계 문서 1번)
  /programs/<id>          -> 상세 (화면설계 문서 2번, 원문/첨부파일 섹션 포함)
"""

import re
import sys
from pathlib import Path

from flask import Flask, render_template, request, abort

sys.path.insert(0, str(Path(__file__).resolve().parent / "db"))
from query import (  # noqa: E402
    get_connection,
    DETAIL_FIELD_ORDER,
    DETAIL_EXTRA_FIELDS,
    CONFIRMATION_DISPLAY_LABELS,
    CONFIRMATION_BADGE_CLASS,
    STATUS_DISPLAY_LABELS,
    SOURCE_DISPLAY_LABELS,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = Flask(__name__)


OFFICIAL_SUPPORT_SOURCES = [
    {
        "name": "정부24 혜택알리미",
        "category": "개인·가족 맞춤 혜택",
        "url": "https://plus.gov.kr/portal/benefitV2",
        "mode": "직접 확인",
        "description": "로그인 후 내 정보에 맞는 정부 혜택을 맞춤 안내받을 수 있습니다.",
        "note": "개인정보 기반 맞춤 안내는 정부24에서 직접 확인합니다.",
    },
    {
        "name": "기업마당",
        "category": "중소기업·소상공인 지원사업",
        "url": "https://www.bizinfo.go.kr/",
        "mode": "자동 연결",
        "description": "현재 앱에서 지원사업 공고를 자동으로 가져오는 기본 출처입니다.",
        "note": "현재 앱의 목록과 검색 결과에 반영됩니다.",
    },
    {
        "name": "K-Startup",
        "category": "창업 지원사업",
        "url": "https://www.k-startup.go.kr/",
        "mode": "일부 연결",
        "description": "창업 지원사업과 창업 관련 공고를 확인할 수 있습니다.",
        "note": "현재 테스트 공고가 앱 데이터에 일부 반영되어 있습니다.",
    },
    {
        "name": "소상공인24",
        "category": "소상공인 지원",
        "url": "https://www.sbiz24.kr/",
        "mode": "직접 확인",
        "description": "소상공인 정책자금과 지원사업 신청·공고를 확인할 수 있습니다.",
        "note": "공식 공개 API가 확인되기 전까지는 사이트에서 직접 확인합니다.",
    },
    {
        "name": "고용24",
        "category": "채용·고용 지원",
        "url": "https://www.work24.go.kr/",
        "mode": "직접 확인",
        "description": "채용, 고용정책, 사업주 지원제도 정보를 확인할 수 있습니다.",
        "note": "직원 수·고용형태 등 조건에 따라 결과가 달라질 수 있습니다.",
    },
    {
        "name": "중소벤처24",
        "category": "중소기업 정책",
        "url": "https://www.smes.go.kr/",
        "mode": "직접 확인",
        "description": "중소기업 정책과 지원 서비스 정보를 확인할 수 있습니다.",
        "note": "공식 공개 API가 확인되면 자동 연결 후보로 검토합니다.",
    },
    {
        "name": "e나라도움",
        "category": "정부 보조금",
        "url": "https://www.gosims.go.kr/",
        "mode": "직접 확인",
        "description": "국고보조금 관련 공고와 신청 정보를 확인할 수 있습니다.",
        "note": "신청 자격과 세부 절차는 해당 사업 공고를 기준으로 확인합니다.",
    },
    {
        "name": "공공데이터포털",
        "category": "공식 API 찾기",
        "url": "https://www.data.go.kr/",
        "mode": "연결 준비",
        "description": "정부기관별 공개 API와 데이터 이용 안내를 찾을 수 있습니다.",
        "note": "공식 API와 서비스키가 확인된 출처만 자동 수집 대상으로 추가합니다.",
    },
]


@app.context_processor
def inject_data_source_meta():
    """
    모든 화면에 공통으로 표시할 데이터 출처 안내.
    "모든 정부지원사업"이라고 표시하지 않고, 이 데이터가 정확히 어디서
    언제까지 수집된 것인지를 항상 함께 보여주기 위한 목적.
    """
    conn = get_connection()
    row = conn.execute(
        """
        SELECT MAX(collected_at) AS ts FROM raw_api_responses
        WHERE source = 'bizinfo' AND response_type = 'page'
        """
    ).fetchone()
    reference_at = row["ts"] if row and row["ts"] else "확인 필요"
    return {
        "data_source_label": "기업마당(bizinfo.go.kr)",
        "collection_reference_at": reference_at,
    }


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    return text.strip()


app.jinja_env.filters["strip_html"] = strip_html
app.jinja_env.filters["confirmation_label"] = lambda v: CONFIRMATION_DISPLAY_LABELS.get(v, v)
app.jinja_env.filters["confirmation_badge_class"] = lambda v: CONFIRMATION_BADGE_CLASS.get(v, "badge-missing")
app.jinja_env.filters["status_label"] = lambda v: STATUS_DISPLAY_LABELS.get(v, v)


def fetch_program_fields(conn, program_id: int) -> dict:
    rows = conn.execute(
        """
        SELECT pf.field_name, pf.field_value, pf.confirmation_status, pf.section_text,
               pf.collected_at, sd.url AS source_url, sd.collected_at AS doc_collected_at,
               sd.content_hash
        FROM program_fields pf
        LEFT JOIN source_documents sd ON sd.id = pf.source_document_id
        WHERE pf.program_id = ?
        """,
        (program_id,),
    ).fetchall()
    # 같은 field_name이 여러 번(이력) 있을 수 있으니 가장 최근 것만 사용
    latest = {}
    for row in rows:
        name = row["field_name"]
        if name not in latest or row["collected_at"] >= latest[name]["collected_at"]:
            latest[name] = row
    return latest


def build_rows(field_map: dict, field_order: list) -> list:
    rows = []
    for label, key in field_order:
        if key.startswith("__missing__:"):
            note = key.split(":", 1)[1]
            rows.append({
                "label": label, "value": None, "confirmation": "미추출",
                "note": note, "source_url": None, "collected_at": None,
            })
            continue
        row = field_map.get(key)
        if not row:
            rows.append({
                "label": label, "value": None, "confirmation": "미추출",
                "note": "수집된 값이 없습니다.", "source_url": None, "collected_at": None,
            })
            continue
        rows.append({
            "label": label,
            "value": row["field_value"],
            "confirmation": row["confirmation_status"],
            "note": row["section_text"],
            "source_url": row["source_url"],
            "collected_at": row["doc_collected_at"] or row["collected_at"],
        })
    return rows


@app.route("/")
def index():
    from flask import redirect, url_for
    return redirect(url_for("program_list"))


@app.route("/support-sources")
def support_sources():
    return render_template(
        "support_sources.html",
        sources=OFFICIAL_SUPPORT_SOURCES,
    )


@app.route("/programs")
def program_list():
    conn = get_connection()
    keyword = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    field_filter = request.args.get("field", "").strip()

    query = """
        SELECT p.id, p.title, p.status_computed, p.application_period_display,
               p.amount_display, p.target_company_display, p.region_display, p.source,
               (SELECT o.name FROM program_organization_roles por
                  JOIN organizations o ON o.id = por.org_id
                  JOIN relationship_types rt ON rt.id = por.role_type_id
                  WHERE por.program_id = p.id AND rt.name = '주관' LIMIT 1) AS org_name
        FROM programs p
        WHERE 1=1
    """
    params = []
    if keyword:
        query += " AND p.title LIKE ?"
        params.append(f"%{keyword}%")
    if status_filter:
        query += " AND p.status_computed = ?"
        params.append(status_filter)
    if field_filter:
        query += """ AND p.id IN (
            SELECT pc.program_id FROM program_classifications pc
            JOIN classification_nodes cn ON cn.id = pc.node_id
            WHERE cn.display_name = ?
        )"""
        params.append(field_filter)
    query += " ORDER BY p.id DESC"

    programs = conn.execute(query, params).fetchall()

    status_options = [r["status_computed"] for r in conn.execute(
        "SELECT DISTINCT status_computed FROM programs ORDER BY status_computed"
    ).fetchall()]
    field_options = [r["display_name"] for r in conn.execute(
        """
        SELECT DISTINCT cn.display_name FROM classification_nodes cn
        JOIN classification_schemes cs ON cs.id = cn.scheme_id
        JOIN classification_axes ca ON ca.id = cs.axis_id
        WHERE ca.name = '지원분야분류' AND cn.parent_node_id IS NULL
        ORDER BY cn.display_name
        """
    ).fetchall()]

    return render_template(
        "list.html",
        programs=programs,
        keyword=keyword,
        status_filter=status_filter,
        field_filter=field_filter,
        status_options=status_options,
        field_options=field_options,
        total=len(programs),
        source_labels=SOURCE_DISPLAY_LABELS,
    )


@app.route("/programs/<int:program_id>")
def program_detail(program_id: int):
    conn = get_connection()
    program = conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone()
    if not program:
        abort(404)

    field_map = fetch_program_fields(conn, program_id)
    detail_rows = build_rows(field_map, DETAIL_FIELD_ORDER)
    extra_rows = build_rows(field_map, DETAIL_EXTRA_FIELDS)

    attachments = conn.execute(
        "SELECT file_name, url FROM source_documents WHERE program_id = ? AND document_type = '첨부파일'",
        (program_id,),
    ).fetchall()
    webpage_doc = conn.execute(
        "SELECT url, collected_at, content_hash FROM source_documents WHERE program_id = ? AND document_type = '웹페이지' LIMIT 1",
        (program_id,),
    ).fetchone()
    orgs = conn.execute(
        """
        SELECT o.name, rt.name AS role FROM program_organization_roles por
        JOIN organizations o ON o.id = por.org_id
        JOIN relationship_types rt ON rt.id = por.role_type_id
        WHERE por.program_id = ?
        """,
        (program_id,),
    ).fetchall()

    return render_template(
        "detail.html",
        program=program,
        detail_rows=detail_rows,
        extra_rows=extra_rows,
        attachments=attachments,
        webpage_doc=webpage_doc,
        orgs=orgs,
        source_labels=SOURCE_DISPLAY_LABELS,
    )


if __name__ == "__main__":
    app.run(debug=True)
