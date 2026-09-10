@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo ================================================
echo   NTIS RND project search and import
echo ================================================
echo.
set KEYWORD=
set /p KEYWORD=Enter a search word, for example startup or AI: 
if not defined KEYWORD goto no_keyword

echo.
echo [1/4] Checking NTIS connection...
python -X utf8 collector\test_ntis_api.py --keyword "%KEYWORD%"
if errorlevel 1 goto failed

echo.
echo [2/4] Downloading NTIS projects...
python -X utf8 collector\fetch_ntis.py --keyword "%KEYWORD%" --display-count 20 --max-pages 5
if errorlevel 1 goto failed

echo.
echo [3/4] Checking database structure...
python -X utf8 app\db\migrate.py
if errorlevel 1 goto failed

echo.
echo [4/4] Importing projects into the app...
python -X utf8 app\db\load_ntis_real.py --commit
if errorlevel 1 goto failed

echo.
echo ================================================
echo   Completed.
echo   Refresh the app page now.
echo ================================================
echo.
pause
exit /b 0

:failed
echo.
echo ================================================
echo   The operation stopped.
echo   Please read the message above.
echo ================================================
echo.
pause
exit /b 1

:no_keyword
echo.
echo No search word was entered.
pause
exit /b 1
