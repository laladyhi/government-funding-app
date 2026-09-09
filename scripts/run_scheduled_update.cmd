@echo off
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0update_all_sources.py"
    exit /b %errorlevel%
)
where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0update_all_sources.py"
    exit /b %errorlevel%
)
"C:\Python314\python.exe" "%~dp0update_all_sources.py"
