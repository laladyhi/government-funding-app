@echo off
chcp 65001 >nul
title 정부지원사업 자동 업데이트 설치
echo.
echo 정부지원사업 자동 업데이트를 설치하고 있습니다.
echo 잠시만 기다려 주세요.
echo.
set "RUNNER=%~dp0scripts\run_scheduled_update.cmd"
schtasks.exe /Create /TN "Government Funding App Update 0930" /SC DAILY /ST 09:30 /TR "%ComSpec% /c %RUNNER%" /F >nul
if errorlevel 1 goto install_failed
schtasks.exe /Create /TN "Government Funding App Update 1530" /SC DAILY /ST 15:30 /TR "%ComSpec% /c %RUNNER%" /F >nul
if errorlevel 1 goto install_failed
echo.
echo 설치가 완료되었습니다.
echo 매일 오전 9시 30분과 오후 3시 30분에 자동으로 업데이트됩니다.
echo.
pause
exit /b 0

:install_failed
echo.
echo 설치에 실패했습니다. 이 창의 내용을 캡처해서 전달해 주세요.
echo.
pause
exit /b 1
