@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title ENARA FULL UPDATE
cd /d "%~dp0"
echo ENARA full collection and app update
echo Only records with announcement title and period will be saved.
echo A database backup will be created before saving.
echo This may take several minutes.
echo.
if exist "C:\Python314\python.exe" (
    set "PY=C:\Python314\python.exe"
) else (
    set "PY=py -3"
)
%PY% -u "%~dp0collector\fetch_enara.py" --full --page-size 1000 --delay 0.4
if errorlevel 1 goto failed
echo.
echo Previewing selected records before database save...
%PY% -u "%~dp0app\db\load_enara_real.py"
if errorlevel 1 goto failed
echo.
echo Saving selected records to the app database...
%PY% -u "%~dp0app\db\load_enara_real.py" --commit
if errorlevel 1 goto failed
echo.
echo ENARA update completed.
goto done
:failed
echo.
echo ENARA update failed. No automatic retry was performed.
:done
echo.
echo Press any key to close.
pause >nul
