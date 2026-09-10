"""
Government Funding AI — Phase 1 로컬 웹 서버 (Flask).

실행: python app/server.py
접속: http://127.0.0.1:5000

화면:
  /                       -> /programs 로 이동
  /programs               -> 목록 + 검색 + 필터 (화면설계 문서 1번)
  /programs/<id>          -> 상세 (화면설계 문서 2번, 원문/첨부파일 섹션 포함)
"""

import math
import re
import sys
from pathlib import Path

from flask import Flask, render_template, request, abort

sys.path.insert(0, str(Path(__file__).resolve().parent / "db"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from query import (  # noqa: E402
    get_connection,
    DETAIL_FIELD_ORDER,
    DETAIL_EXTRA_FIELDS,
    CONFIRMATION_DISPLAY_LABELS,
    CONFIRMATION_BADGE_CLASS,
    STATUS_DISPLAY_LABELS,
    SOURCE_DISPLAY_LABELS,
)
from action_summary import build_action_summary, truncate_ko  # noqa: E402
from deadline_status import get_deadline_status, deadline_sort_key  # noqa: E402
from region_matching import build_region_index, matches_region  # noqa: E402
from company_matching import (  # noqa: E402
    match_company_to_all_programs,
    VERDICT_GOOD,
    VERDICT_REVIEW,
    VERDICT_MISMATCH,
    DIMENSION_LABELS,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = Flask(__name__)
app.jinja_env.filters["truncate_ko"] = truncate_ko

PAGE_SIZE = 20


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
    {
        "name": "e나라도움·보조금통합포털",
        "category": "국고보조금·공모사업",
        "url": "https://www.bojo.go.kr/bojo.do",
        "mode": "연결 준비",
        "description": "국고보조사업 공모·지원정보를 확인할 수 있는 공식 포털입니다.",
        "note": "공식 API 승인 및 명세 확인 후 자동 수집 대상으로 추가합니다.",
    },
]


@app.context_processor
def inject_data_source_meta():
    """
    모든 화면에 공통으로 표시할 데이터 출처 안내.
    "모든 정부지원사업"이라고 표시하지 않고, 이 데이터가 정확히 어느
    출처에서 언제까지 수집된 것인지 출처별로 보여주기 위한 목적.

    2026-09-07: 출처가 기업마당 하나에서 4개(기업마당·K-Startup·정부24
    공공서비스(혜택)·KOCCA)로 늘었는데, 이 안내가 여전히 기업마당 하나만
    가리키고 있어서(문구도 "기업마당에 연계된"으로 고정, 수집 기준일도
    raw_api_responses의 bizinfo 'page' 응답만 조회) 나머지 3개 출처
    데이터가 실제로 있는데도 없는 것처럼 보이는 문제가 있었다. programs
    테이블 기준으로 출처별 건수·최근 수집 시각을 전부 계산해 일반화한다.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS cnt, MAX(last_updated_at) AS latest
        FROM programs
        GROUP BY source
        ORDER BY source
        """
    ).fetchall()
    source_summaries = [
        {
            "label": SOURCE_DISPLAY_LABELS.get(r["source"], r["source"]),
            "count": r["cnt"],
            "latest": r["latest"] or "확인 필요",
        }
        for r in rows
    ]
    return {"source_summaries": source_summaries}


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


COMPANY_TYPE_OPTIONS = ["소상공인", "중소기업", "중견기업", "해당없음", "확인 필요"]
YES_NO_OPTIONS = ["예", "아니오", "확인 필요"]


def _int_or_none(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_company_form(form) -> tuple:
    """
    company_profiles INSERT/UPDATE에 그대로 쓸 수 있는 값 튜플을 만든다.
    company_type/exports/rnd는 DB의 CHECK 제약과 정확히 같은 값만
    허용된다 — 폼이 예상 밖의 값(빈 문자열, 인코딩이 깨진 값 등)을
    보내면 여기서 안전한 기본값으로 걸러내야 한다. 이걸 안 하면
    sqlite3.IntegrityError가 그대로 튀어 올라 500 에러 화면이 뜨고,
    그 요청이 재시도되는 경우 빈 프로필이 반복 저장될 위험이 있다
    (2026-09-09 테스트 중 실제로 겪은 문제).
    """
    submitted_type = form.get("company_type", "")
    company_type = submitted_type if submitted_type in COMPANY_TYPE_OPTIONS else "확인 필요"
    submitted_exports = form.get("exports", "")
    exports = submitted_exports if submitted_exports in YES_NO_OPTIONS else "확인 필요"
    submitted_rnd = form.get("rnd", "")
    rnd = submitted_rnd if submitted_rnd in YES_NO_OPTIONS else "확인 필요"
    name = form.get("name", "").strip() or "이름 없는 회사"
    return (
        name,
        form.get("region", "").strip() or None,
        form.get("industry", "").strip() or None,
        form.get("founded_date", "").strip() or None,
        _int_or_none(form.get("business_age_years")),
        _int_or_none(form.get("employee_count")),
        form.get("revenue_range", "").strip() or None,
        company_type,
        exports,
        rnd,
        form.get("desired_fields", "").strip() or None,
    )


@app.route("/company-profile", methods=["GET", "POST"])
def company_profile():
    """
    회사 프로필 입력/목록 화면. 여기서 저장하는 값은 company_profiles
    표(2026-09-09 새로 추가, 마이그레이션 0006)에만 들어가고, 기존
    지원사업 표(programs 등)는 전혀 건드리지 않는다.
    """
    conn = get_connection()
    if request.method == "POST":
        values = _parse_company_form(request.form)
        conn.execute(
            """
            INSERT INTO company_profiles (
              name, region, industry, founded_date, business_age_years,
              employee_count, revenue_range, company_type, exports, rnd, desired_fields
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        conn.commit()
        from flask import redirect, url_for
        return redirect(url_for("company_profile"))

    profiles = conn.execute("SELECT * FROM company_profiles ORDER BY id DESC").fetchall()
    return render_template(
        "company_profile.html",
        profiles=profiles,
        edit_profile=None,
        company_type_options=COMPANY_TYPE_OPTIONS,
        yes_no_options=YES_NO_OPTIONS,
    )


@app.route("/company-profile/<int:company_id>/edit", methods=["GET", "POST"])
def company_profile_edit(company_id):
    """저장된 회사 프로필 하나를 수정한다. company_profiles 표만 갱신한다."""
    conn = get_connection()
    existing = conn.execute("SELECT * FROM company_profiles WHERE id = ?", (company_id,)).fetchone()
    if not existing:
        abort(404)

    if request.method == "POST":
        values = _parse_company_form(request.form)
        conn.execute(
            """
            UPDATE company_profiles SET
              name = ?, region = ?, industry = ?, founded_date = ?, business_age_years = ?,
              employee_count = ?, revenue_range = ?, company_type = ?, exports = ?, rnd = ?,
              desired_fields = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            values + (company_id,),
        )
        conn.commit()
        from flask import redirect, url_for
        return redirect(url_for("company_profile"))

    profiles = conn.execute("SELECT * FROM company_profiles ORDER BY id DESC").fetchall()
    return render_template(
        "company_profile.html",
        profiles=profiles,
        edit_profile=dict(existing),
        company_type_options=COMPANY_TYPE_OPTIONS,
        yes_no_options=YES_NO_OPTIONS,
    )


@app.route("/company-profile/<int:company_id>/delete", methods=["POST"])
def company_profile_delete(company_id):
    """저장된 회사 프로필 하나를 삭제한다. company_profiles 표만 건드린다(POST 전용)."""
    conn = get_connection()
    conn.execute("DELETE FROM company_profiles WHERE id = ?", (company_id,))
    conn.commit()
    from flask import redirect, url_for
    return redirect(url_for("company_profile"))


@app.route("/company-profile/<int:company_id>/match")
def company_match(company_id):
    """
    저장된 회사 프로필 하나를 기준으로 전체 지원사업과 비교한다.
    AI/외부 API 호출 없음 — app/db/company_matching.py의 규칙 비교만 사용.
    programs 등 기존 표는 조회만 하고 쓰지 않는다.
    """
    conn = get_connection()
    row = conn.execute("SELECT * FROM company_profiles WHERE id = ?", (company_id,)).fetchone()
    if not row:
        abort(404)
    company = dict(row)
    all_results = match_company_to_all_programs(conn, company)
    counts = {VERDICT_GOOD: 0, VERDICT_REVIEW: 0, VERDICT_MISMATCH: 0}
    for r in all_results:
        counts[r["verdict"]] += 1

    # 목록 화면과 동일하게 페이지당 PAGE_SIZE(20)건만 렌더링한다 — 전체
    # 2천 건 이상을 한 화면에 그대로 그리면 목록 화면과 같은 문제(과도한
    # 스크롤·느린 렌더링)가 재현된다. 정렬(적합 가능성 높음 우선)은
    # match_company_to_all_programs()가 이미 해 둔 상태를 그대로 쓴다.
    total_count = len(all_results)
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE))
    page = request.args.get("page", 1, type=int) or 1
    page = min(max(page, 1), total_pages)
    offset = (page - 1) * PAGE_SIZE
    results = all_results[offset: offset + PAGE_SIZE]

    return render_template(
        "match_results.html",
        company=company,
        results=results,
        counts=counts,
        total_count=total_count,
        page=page,
        total_pages=total_pages,
        dimension_labels=DIMENSION_LABELS,
        source_labels=SOURCE_DISPLAY_LABELS,
    )


@app.route("/programs/profile", methods=["POST"])
def inline_company_profile():
    """목록 화면 안에서 회사 정보를 저장하고 바로 매칭하기 위한 처리."""
    conn = get_connection()
    submitted_type = request.form.get("company_type", "")
    company_type = submitted_type if submitted_type in COMPANY_TYPE_OPTIONS else "확인 필요"
    submitted_exports = request.form.get("exports", "")
    exports = submitted_exports if submitted_exports in YES_NO_OPTIONS else "확인 필요"
    submitted_rnd = request.form.get("rnd", "")
    rnd = submitted_rnd if submitted_rnd in YES_NO_OPTIONS else "확인 필요"

    values = (
        request.form.get("name", "").strip() or "이름 없는 회사",
        request.form.get("region", "").strip() or None,
        request.form.get("industry", "").strip() or None,
        request.form.get("founded_date", "").strip() or None,
        _int_or_none(request.form.get("business_age_years")),
        _int_or_none(request.form.get("employee_count")),
        request.form.get("revenue_range", "").strip() or None,
        company_type,
        exports,
        rnd,
        request.form.get("desired_fields", "").strip() or None,
    )
    profile_id = _int_or_none(request.form.get("profile_id"))
    if profile_id and conn.execute(
        "SELECT 1 FROM company_profiles WHERE id = ?", (profile_id,)
    ).fetchone():
        conn.execute(
            """
            UPDATE company_profiles
            SET name=?, region=?, industry=?, founded_date=?, business_age_years=?,
                employee_count=?, revenue_range=?, company_type=?, exports=?, rnd=?,
                desired_fields=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            values + (profile_id,),
        )
    else:
        conn.execute(
            """
            INSERT INTO company_profiles (
              name, region, industry, founded_date, business_age_years,
              employee_count, revenue_range, company_type, exports, rnd, desired_fields
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        profile_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    from flask import redirect, url_for
    return redirect(url_for("program_list", profile_id=profile_id))


@app.route("/programs")
def program_list():
    conn = get_connection()
    keyword = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    field_filter = request.args.get("field", "").strip()
    source_filter = request.args.get("source", "").strip()
    region_filter = request.args.get("region", "").strip()
    profile_id = request.args.get("profile_id", type=int)
    match_view = request.args.get("view", "matched").strip()
    if match_view not in ("matched", "all"):
        match_view = "matched"

    # 저장된 회사가 있으면 일반적인 /programs 접속도 가장 최근 프로필의
    # 맞춤 사업부터 보여준다. 사용자가 명시적으로 view=all을 요청한 경우만
    # 전체 목록으로 시작한다.
    if not profile_id and match_view != "all":
        latest_profile = conn.execute(
            "SELECT id FROM company_profiles ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if latest_profile:
            profile_id = latest_profile["id"]

    where_clause = "1=1"
    params = []
    if keyword:
        where_clause += " AND p.title LIKE ?"
        params.append(f"%{keyword}%")
    if status_filter:
        where_clause += " AND p.status_computed = ?"
        params.append(status_filter)
    if field_filter:
        where_clause += """ AND p.id IN (
            SELECT pc.program_id FROM program_classifications pc
            JOIN classification_nodes cn ON cn.id = pc.node_id
            WHERE cn.display_name = ?
        )"""
        params.append(field_filter)
    if source_filter:
        where_clause += " AND p.source = ?"
        params.append(source_filter)

    query = f"""
        SELECT p.id, p.title, p.status_computed, p.application_period_display,
               p.amount_display, p.target_company_display, p.region_display,
               p.source, p.source_item_id,
               (SELECT o.name FROM program_organization_roles por
                  JOIN organizations o ON o.id = por.org_id
                  JOIN relationship_types rt ON rt.id = por.role_type_id
                  WHERE por.program_id = p.id AND rt.name = '주관' LIMIT 1) AS org_name
        FROM programs p
        WHERE {where_clause}
        ORDER BY p.id DESC
    """
    all_programs = [dict(r) for r in conn.execute(query, params).fetchall()]
    if region_filter:
        region_index = build_region_index(conn)
        all_programs = [
            p for p in all_programs
            if matches_region(
                [p.get("region_display"), *region_index.get(p["id"], set())],
                region_filter,
            )
        ]

    company_profile = None
    match_counts = {VERDICT_GOOD: 0, VERDICT_REVIEW: 0, VERDICT_MISMATCH: 0}
    matches_by_program = {}
    if profile_id:
        profile_row = conn.execute(
            "SELECT * FROM company_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if profile_row:
            company_profile = dict(profile_row)
            all_matches = match_company_to_all_programs(conn, company_profile)
            for result in all_matches:
                match_counts[result["verdict"]] += 1
            matches_by_program = {r["program_id"]: r for r in all_matches}
            if match_view != "all":
                all_programs = [
                    p for p in all_programs
                    if matches_by_program.get(p["id"], {}).get("verdict")
                    in (VERDICT_GOOD, VERDICT_REVIEW)
                ]

    for p in all_programs:
        p["deadline_state"] = get_deadline_status(p.get("application_period_display") or "")
        p["match_result"] = matches_by_program.get(p["id"])

    if company_profile:
        priority_order = {VERDICT_GOOD: 0, VERDICT_REVIEW: 1, VERDICT_MISMATCH: 2}
        all_programs.sort(key=lambda p: (
            priority_order.get(
                (p.get("match_result") or {}).get("verdict"), 3
            ),
            # 회사 조건 일치 수가 많을수록 위로, 확인 필요 항목이
            # 적을수록 위로. 마감일은 같은 적합도일 때만 보조한다.
            -(p.get("match_result") or {}).get("matched_count", 0),
            (p.get("match_result") or {}).get("review_count", 99),
            (p.get("match_result") or {}).get("mismatch_count", 99),
            *deadline_sort_key(p),
        ))
    else:
        all_programs.sort(key=deadline_sort_key)

    # 출처가 늘어나 전체 건수가 많아져도 한 페이지에는 PAGE_SIZE건만 표시한다.
    total_count = len(all_programs)
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE))
    page = request.args.get("page", 1, type=int) or 1
    page = min(max(page, 1), total_pages)
    offset = (page - 1) * PAGE_SIZE
    programs = all_programs[offset: offset + PAGE_SIZE]
    for p in programs:
        p["summary"] = build_action_summary(conn, p)

    company_profiles = [dict(r) for r in conn.execute(
        "SELECT id, name FROM company_profiles ORDER BY id DESC"
    ).fetchall()]

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
    source_options = [r["source"] for r in conn.execute(
        "SELECT DISTINCT source FROM programs ORDER BY source"
    ).fetchall()]

    return render_template(
        "list.html",
        programs=programs,
        keyword=keyword,
        status_filter=status_filter,
        field_filter=field_filter,
        source_filter=source_filter,
        region_filter=region_filter,
        profile_id=profile_id,
        match_view=match_view,
        company_profile=company_profile,
        company_profiles=company_profiles,
        match_counts=match_counts,
        matched_total=match_counts[VERDICT_GOOD] + match_counts[VERDICT_REVIEW],
        dimension_labels=DIMENSION_LABELS,
        company_type_options=COMPANY_TYPE_OPTIONS,
        yes_no_options=YES_NO_OPTIONS,
        status_options=status_options,
        field_options=field_options,
        source_options=source_options,
        total=total_count,
        page=page,
        total_pages=total_pages,
        page_size=PAGE_SIZE,
        source_labels=SOURCE_DISPLAY_LABELS,
    )


@app.route("/programs/<int:program_id>")
def program_detail(program_id: int):
    conn = get_connection()
    program_row = conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone()
    if not program_row:
        abort(404)
    program = dict(program_row)
    program["summary"] = build_action_summary(conn, program)

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
    # 일반 사용자는 앱을 한 번만 실행해야 하므로 Flask 자동 재실행을 끈다.
    # debug/reloader가 켜져 있으면 Python 프로세스가 두 개로 늘어나
    # SQLite를 동시에 사용하면서 "database is locked"가 발생하기 쉽다.
    app.run(debug=False, use_reloader=False)
