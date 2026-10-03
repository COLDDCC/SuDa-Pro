@echo off
REM Double-click to start the backend. First run creates .venv and installs packages.
cd /d "%~dp0"

if not exist ".venv\installed.ok" (
    echo [1/2] First run: creating .venv and installing packages, please wait 1-2 min...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || goto :error
    echo ok> ".venv\installed.ok"
)

if "%STAFF_KEY%"=="" set STAFF_KEY=test123
echo [2/2] Starting backend on http://127.0.0.1:8811   STAFF_KEY=%STAFF_KEY%
echo       Keep this window open. Admin page: http://127.0.0.1:8811/admin/
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8811
pause
exit /b 0

:error
echo.
echo [FAILED] See the first error message above.
pause
exit /b 1
