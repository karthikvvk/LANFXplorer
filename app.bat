@echo off
setlocal enabledelayedexpansion

REM ===============================================
REM LANFXplorer Windows Application Launcher
REM ===============================================

REM Get the directory where this script is located
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

set "OPENSSL_PREFIX=%APP_DIR%\opt\openssl"
set "PY_PREFIX=%APP_DIR%\opt\python39"

REM -------------------------------
REM Set environment variables
REM -------------------------------

REM Add Python and OpenSSL to PATH
REM Note: OpenSSL DLLs are in the root openssl directory, binaries are in bin subdirectory
set "PATH=%OPENSSL_PREFIX%;%OPENSSL_PREFIX%\bin;%PY_PREFIX%;%PY_PREFIX%\Scripts;%PATH%"

REM Set Python environment variables
set "PYTHONHOME=%PY_PREFIX%"
set "PYTHONPATH=%APP_DIR%"

REM Set OpenSSL environment variables
set "OPENSSL_CONF=%OPENSSL_PREFIX%\bin\openssl.cfg"

REM -------------------------------
REM Launch the application
REM -------------------------------

echo [*] Starting LANFXplorer...
echo     Python: %PY_PREFIX%\python.exe
echo     App Directory: %APP_DIR%
echo.

REM Check if Python exists
if not exist "%PY_PREFIX%\python.exe" (
    echo [!] Error: Python not found at %PY_PREFIX%
    echo     Please run install.bat first to set up the application.
    pause
    exit /b 1
)

REM Run the main application
"%PY_PREFIX%\python.exe" "%APP_DIR%\main.py"

REM Keep window open if there was an error
if %errorlevel% neq 0 (
    echo.
    echo [!] Application exited with error code %errorlevel%
    pause
)
