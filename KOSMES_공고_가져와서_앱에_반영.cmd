@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo ================================================
echo   KOSMES support notice import
echo ================================================
echo.
set KEYWORD=
set /p KEYWORD=Enter a hashtag, or press Enter for all: 
echo.
echo [1/3] Downloading KOSMES notices...
if defined KEYWORD (python -X utf8 collector\fetch_kosmes.py --hashtag "%KEYWORD%" --page-size 20 --max-pages 5) else (python -X utf8 collector\fetch_kosmes.py --page-size 20 --max-pages 5)
if errorlevel 1 goto failed
echo.
echo [2/3] Checking database structure...
python -X utf8 app\db\migrate.py
if errorlevel 1 goto failed
echo.
echo [3/3] Importing notices into the app...
python -X utf8 app\db\load_kosmes_real.py --commit
if errorlevel 1 goto failed
echo.
echo Completed. Refresh the app page now.
pause
exit /b 0
:failed
echo.
echo The operation stopped. Please read the message above.
pause
exit /b 1
