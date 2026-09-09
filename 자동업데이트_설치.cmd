@echo off
setlocal
title Government Funding App Update Setup

echo.
echo Installing the twice-daily update schedule...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_twice_daily_update.ps1"
if errorlevel 1 goto install_failed

echo.
echo INSTALLATION COMPLETED.
echo The update will run every day at 09:30 and 15:30.
echo.
pause
exit /b 0

:install_failed
echo.
echo INSTALLATION FAILED.
echo Please right-click this file and choose "Run as administrator".
echo.
pause
exit /b 1
