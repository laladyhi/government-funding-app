"""4개 출처의 최신 자료를 수집하고 운영 DB에 반영하는 자동 업데이트 작업."""

import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "collector" / "logs"
DB_PATH = PROJECT_ROOT / "app" / "data" / "govfunding.sqlite3"
BACKUP_DIR = PROJECT_ROOT / "app" / "data" / "backups"


def has_env_value(name: str) -> bool:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{name}="):
            return bool(line.split("=", 1)[1].strip())
    return False


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"scheduled_update_{stamp}.log"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"govfunding_before_all_sources_{stamp}.sqlite3"
    shutil.copyfile(DB_PATH, backup_path)
    python = sys.executable
    steps = [
        [python, "collector/fetch_and_store.py", "--full", "--delay", "0.4"],
        [python, "app/db/load_bizinfo.py"],
        [python, "collector/fetch_kstartup.py", "--full", "--delay", "0.4"],
        [python, "app/db/load_kstartup_real.py", "--commit"],
        [python, "collector/fetch_public_benefits.py", "--full", "--delay", "0.4"],
        [python, "app/db/load_public_benefits_real.py", "--commit"],
        [python, "collector/fetch_kocca.py", "--full", "--delay", "0.4"],
        [python, "app/db/load_kocca_all.py", "--commit"],
    ]
    if has_env_value("ENARA_API_KEY"):
        steps.extend([
            [python, "collector/fetch_enara.py", "--full", "--delay", "0.4"],
            [python, "app/db/load_enara_real.py", "--commit"],
        ])
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"자동 업데이트 시작: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        log.write(f"전체 작업 전 백업: {backup_path}\n")
        for step in steps:
            log.write(f"\n$ {' '.join(step[1:])}\n")
            result = subprocess.run(step, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8")
            log.write(result.stdout or "")
            log.write(result.stderr or "")
            if result.returncode != 0:
                log.write(f"\n자동 업데이트 중단: exit={result.returncode}\n")
                print(f"[실패] 자동 업데이트가 중단되었습니다. 로그: {log_path}")
                return result.returncode
        log.write(f"\n자동 업데이트 완료: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    print(f"[완료] 4개 출처 자동 업데이트가 끝났습니다. 로그: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
