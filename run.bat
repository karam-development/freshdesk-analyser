@echo off
REM ============================================================
REM Freshdesk AI Analyzer - Web App
REM Double-click this file to start
REM ============================================================

cd /d "%~dp0"

python -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

echo.
echo ==========================================
echo   Freshdesk AI Analyzer
echo   Starting web app...
echo ==========================================
echo.
echo   Open your browser to:
echo   http://localhost:5000
echo.
echo   Press Ctrl+C to stop
echo ==========================================
echo.

python app.py
pause
