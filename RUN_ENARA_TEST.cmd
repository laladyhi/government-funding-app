@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title ENARA API TEST
cd /d "%~dp0"
echo ENARA API test starting...
echo Only up to 5 records will be requested. The database will not be changed.
echo Running folder: %CD%
echo.

where py >nul 2>&1
if not errorlevel 1 (
    echo Python: py -3
    py -3 -u "%~dp0collector\test_enara_api.py"
    set "TEST_EXIT=!ERRORLEVEL!"
    goto done
)

where python >nul 2>&1
if not errorlevel 1 (
    echo Python: python
    python -u "%~dp0collector\test_enara_api.py"
    set "TEST_EXIT=!ERRORLEVEL!"
    goto done
)

if exist "C:\Python314\python.exe" (
    echo Python: C:\Python314\python.exe
    "C:\Python314\python.exe" -u "%~dp0collector\test_enara_api.py"
    set "TEST_EXIT=!ERRORLEVEL!"
    goto done
)

echo Python was not found on this computer.
set "TEST_EXIT=1"

:done
echo.
echo Test exit code: !TEST_EXIT!
echo Test finished. Press any key to close this window.
pause >nul
