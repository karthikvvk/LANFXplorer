@echo off
setlocal

REM ===============================================
REM LANFXplorer Windows Application Launcher
REM ===============================================

REM Get the directory where this script is located
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

set "PY_PREFIX=%APP_DIR%\opt\python39"
set "PYTHON_EXE=%PY_PREFIX%\python.exe"

REM -------------------------------
REM Launch the application
REM -------------------------------

echo [*] Starting LANFXplorer...
echo     App Directory: %APP_DIR%
echo.

REM Use embedded Python installed by install.bat
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at: %PYTHON_EXE%
    echo         Please run install.bat first.
    pause
    exit /b 1
)

echo [*] Using Python: %PYTHON_EXE%

REM Set up environment for embedded Python
REM NOTE: Do NOT set PYTHONHOME - embedded Python uses ._pth files for path config
REM Setting PYTHONHOME breaks DLL loading for native extensions like cryptography
set "PYTHONPATH=%APP_DIR%"
set "PATH=%PY_PREFIX%;%PY_PREFIX%\Scripts;%PATH%"

REM Make system OpenSSL CLI available via env var (but NOT on PATH to avoid DLL conflicts)
REM The cryptography package bundles its own OpenSSL DLLs - system OpenSSL on PATH causes version mismatch
set "OPENSSL_PATH=C:\Program Files\OpenSSL-Win64\bin\openssl.exe"

REM Run the main application
"%PYTHON_EXE%" "%APP_DIR%\main.py"

REM Keep window open if there was an error
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
