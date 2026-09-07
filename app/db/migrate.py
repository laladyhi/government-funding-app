"""
SQLite 마이그레이션 실행기.

사용법:
  python app/db/migrate.py

동작:
  - app/db/migrations/*.sql 파일들을 파일명 순서대로 확인한다.
  - 아직 적용되지 않은 파일만 실행한다 (schema_migrations 테이블로 추적).
  - 이미 적용된 파일은 다시 실행하지 않으므로, 여러 번 실행해도 안전하다.
  - 기존 데이터를 지우지 않는다 — 새 마이그레이션 파일을 추가하는 방식으로
    스키마를 바꿔나간다 (예: 0002_add_xxx.sql).
"""

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def applied_versions(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def run_migrations() -> int:
    conn = get_connection()
    ensure_migrations_table(conn)
    already_applied = applied_versions(conn)

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print(f"[정보] 마이그레이션 파일이 없습니다: {MIGRATIONS_DIR}")
        return 0

    applied_count = 0
    for path in migration_files:
        version = path.name
        if version in already_applied:
            print(f"[건너뜀] 이미 적용됨: {version}")
            continue

        sql_text = path.read_text(encoding="utf-8")
        print(f"[적용중] {version}")
        try:
            conn.executescript(sql_text)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
            conn.commit()
            applied_count += 1
            print(f"[완료] {version}")
        except sqlite3.Error as exc:
            conn.rollback()
            print(f"[실패] {version} — {exc}")
            return 1

    print(f"\n[결과] 총 {applied_count}개 마이그레이션 적용, DB 위치: {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(run_migrations())
