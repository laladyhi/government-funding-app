@echo off
chcp 65001 >nul
title 정부지원사업 전체 데이터 업데이트
cd /d "%~dp0"

echo 전체 데이터를 수집하고 있습니다.
echo 기관별 자료량에 따라 시간이 걸릴 수 있습니다.
echo 창을 닫지 마세요.
echo.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0scripts\update_all_sources.py"
    goto update_done
)
where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0scripts\update_all_sources.py"
    goto update_done
)
if exist "C:\Python314\python.exe" (
    "C:\Python314\python.exe" "%~dp0scripts\update_all_sources.py"
    goto update_done
)
echo Python을 찾지 못했습니다.

:update_done
echo.
if errorlevel 1 (
    echo 업데이트에 실패했습니다. collector\logs 폴더의 로그를 확인해야 합니다.
) else (
    echo 전체 업데이트가 완료되었습니다.
    echo 앱 화면을 새로고침하면 최신 자료를 볼 수 있습니다.
)
echo.
pause
