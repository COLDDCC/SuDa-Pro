@echo off
REM Double-click to run the smoke test. Start start_backend.bat first and keep it open.
cd /d "%~dp0"

if not exist ".venv\installed.ok" (
    echo Please double-click start_backend.bat first.
    pause
    exit /b 1
)

if "%STAFF_KEY%"=="" set STAFF_KEY=test123
".venv\Scripts\python.exe" scripts\smoke_test.py
pause
