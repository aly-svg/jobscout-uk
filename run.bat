@echo off
REM ============================================================
REM  JobScout UK - double-click to start
REM ============================================================
cd /d "%~dp0"
if not exist .venv (
    echo First time? Run setup.bat once before using run.bat
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
echo Starting JobScout UK... your browser will open automatically.
echo Keep this black window open while you use the app. Close it to quit.
python app.py
pause
