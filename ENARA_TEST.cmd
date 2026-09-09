@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title ENARA API TEST
cd /d "%~dp0"
echo ENARA API connection test
echo Folder: %CD%
echo Database will not be changed.
echo.
if exist "C:\Python314\python.exe" (
    echo Starting Python: C:\Python314\python.exe
    "C:\Python314\python.exe" -u "%~dp0collector\test_enara_api.py"
    set "RC=!ERRORLEVEL!"
    goto finished
)
echo Trying Python launcher...
py -3 -u "%~dp0collector\test_enara_api.py"
set "RC=!ERRORLEVEL!"
if not !RC! == 9009 goto finished
echo Trying python command...
python -u "%~dp0collector\test_enara_api.py"
set "RC=!ERRORLEVEL!"
:finished
echo.
echo Exit code: !RC!
echo Test finished. Press any key to close.
pause >nul
