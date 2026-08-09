@echo off
REM ============================================================
REM  JobScout UK - one-time setup (run this ONCE, then use run.bat)
REM ============================================================
cd /d "%~dp0"
echo.
echo [1/3] Checking Python...
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python is not installed or not on PATH.
    echo   Download it from https://www.python.org/downloads/windows/
    echo   IMPORTANT: tick "Add python.exe to PATH" during install.
    echo   Then run this setup.bat again.
    pause
    exit /b 1
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo   Your Python is older than 3.10. Please install Python 3.11+ from python.org.
    pause
    exit /b 1
)
echo [2/3] Creating private environment (first time only)...
if not exist .venv (
    py -3 -m venv .venv
)
echo [3/3] Installing components (2-5 minutes on first run)...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo   Install failed. Check your internet connection and re-run setup.bat
    pause
    exit /b 1
)
echo.
echo ============================================================
echo  Setup complete. From now on just double-click run.bat
echo ============================================================
pause
