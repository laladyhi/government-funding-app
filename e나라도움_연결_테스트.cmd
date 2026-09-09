@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title e나라도움 API 연결 테스트
cd /d "%~dp0"

echo e나라도움 API 연결을 확인합니다.
echo 최대 5건만 조회하며 운영 DB에는 저장하지 않습니다.
echo 실행 위치: %CD%
echo.
where py >nul 2>&1
if not errorlevel 1 (
    echo Python 실행: py -3
    py -3 -u "%~dp0collector\test_enara_api.py"
    set "TEST_EXIT=!ERRORLEVEL!"
    goto test_done
)

where python >nul 2>&1
if not errorlevel 1 (
    echo Python 실행: python
    python -u "%~dp0collector\test_enara_api.py"
    set "TEST_EXIT=!ERRORLEVEL!"
    goto test_done
)

if exist "C:\Python314\python.exe" (
    echo Python 실행: C:\Python314\python.exe
    "C:\Python314\python.exe" -u "%~dp0collector\test_enara_api.py"
    set "TEST_EXIT=!ERRORLEVEL!"
    goto test_done
)

echo Python을 찾지 못했습니다.
echo 먼저 Python 설치가 필요합니다.
set "TEST_EXIT=1"

:test_done
echo.
echo 테스트 종료 코드: !TEST_EXIT!
echo 테스트가 끝났습니다. 위 결과를 확인해 주세요.
pause
