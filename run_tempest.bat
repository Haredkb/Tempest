@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  Tempest 1D -- Launcher  (no admin required)
echo ============================================================

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Virtual environment in user home -- always writable, no admin
set "VENV_DIR=%USERPROFILE%\tempest_venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

REM ================================================================
REM  STEP 1: If venv already has streamlit, just launch
REM ================================================================
if exist "%VENV_PY%" (
    "%VENV_PY%" -m streamlit --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [OK] Virtual env ready at %VENV_DIR%
        goto :launch
    )
)

REM ================================================================
REM  STEP 2: Find a Python executable
REM ================================================================
set "PYTHON_EXE="

REM Try 'python' on PATH first
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 ( set "PYTHON_EXE=python" & goto :python_found )

REM Try 'python3'
python3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 ( set "PYTHON_EXE=python3" & goto :python_found )

REM Try well-known install locations (ARM64 + x64, 3.11 / 3.12 / 3.13)
for %%P in (
    "%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python313-arm64\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python312-arm64\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\ProgramData\Anaconda3\python.exe"
    "%USERPROFILE%\Anaconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\AppData\Local\anaconda3\python.exe"
    "%USERPROFILE%\AppData\Local\miniconda3\python.exe"
) do (
    if exist %%P ( set "PYTHON_EXE=%%~P" & goto :python_found )
)

echo [ERROR] Cannot find Python. Install Python 3.11+ from https://python.org
echo         and re-run this script.
pause
exit /b 1

:python_found
echo [INFO] Using Python: %PYTHON_EXE%

REM ================================================================
REM  STEP 3: Create virtual environment
REM ================================================================
if not exist "%VENV_DIR%" (
    echo [INFO] Creating virtual environment at %VENV_DIR% ...
    "%PYTHON_EXE%" -m venv "%VENV_DIR%"
    if !ERRORLEVEL! NEQ 0 (
        echo [ERROR] venv creation failed.
        pause
        exit /b 1
    )
)

REM ================================================================
REM  STEP 4: Install packages  (--prefer-binary avoids C compilation)
REM ================================================================
echo [INFO] Installing packages (first run takes a few minutes)...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install ^
    "streamlit>=1.28" "pandas>=1.5" "numpy>=1.23" ^
    "matplotlib>=3.6" "scipy>=1.9" "filterpy>=1.4.5" ^
    --prefer-binary --progress-bar on

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Package install failed. See messages above.
    pause
    exit /b 1
)
echo [OK] Packages installed.

:launch
echo.
echo [INFO] Starting Tempest app...
echo [INFO] Browser opens automatically at http://localhost:8501
echo [INFO] Press Ctrl+C in this window to stop.
echo.
"%VENV_PY%" -m streamlit run "%SCRIPT_DIR%\tempest_app.py"

endlocal
