@echo off
chcp 65001 >nul
title 정부지원사업 앱
cd /d "%~dp0"

echo 정부지원사업 앱을 시작하고 있습니다.
echo 잠시만 기다려 주세요.

where py >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto python_found
)
where python >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto python_found
)
if exist "C:\Python314\python.exe" (
    set "PY=C:\Python314\python.exe"
    goto python_found
)
echo Python을 찾지 못했습니다. Python 3.10 이상을 설치한 뒤 다시 실행하세요.
pause
exit /b 1

:python_found
if not exist "%~dp0app\data\govfunding.sqlite3" (
    echo.
    echo 처음 실행이라 준비 작업을 진행합니다. 잠시 기다려 주세요.
    echo [1/2] 필요한 패키지를 설치합니다...
    %PY% -m pip install -r "%~dp0requirements.txt" -q
    echo [2/2] 데이터베이스를 생성합니다...
    %PY% "%~dp0app\db\migrate.py"
    echo 준비가 끝났습니다.
    echo.
)

start "Government Funding App" /min %PY% "%~dp0app\server.py"
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:5000/programs"

echo 앱이 실행되었습니다.
echo 브라우저에서 지원사업 목록을 확인하세요.
echo 이 창은 앱을 종료할 때까지 닫지 않아도 됩니다.
pause
