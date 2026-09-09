@echo off
chcp 65001 >nul
title 정부지원사업 앱
cd /d "%~dp0"

echo 정부지원사업 앱을 시작하고 있습니다.
echo 잠시만 기다려 주세요.

where py >nul 2>&1
if not errorlevel 1 (
    start "Government Funding App" /min py -3 "%~dp0app\server.py"
    goto app_started
)
where python >nul 2>&1
if not errorlevel 1 (
    start "Government Funding App" /min python "%~dp0app\server.py"
    goto app_started
)
if exist "C:\Python314\python.exe" (
    start "Government Funding App" /min "C:\Python314\python.exe" "%~dp0app\server.py"
    goto app_started
)
echo Python을 찾지 못했습니다.
pause
exit /b 1

:app_started
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:5000/programs"

echo 앱이 실행되었습니다.
echo 브라우저에서 지원사업 목록을 확인하세요.
echo 이 창은 앱을 종료할 때까지 닫지 않아도 됩니다.
pause
